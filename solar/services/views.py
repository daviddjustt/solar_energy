import os
import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from solar.services.models import (
    ServiceRequest, ServiceAttachment, ServicePendency, 
    ServiceObservation, ServiceStatusHistory, ServiceType
)
from solar.services.serializers import (
    ServiceRequestSerializer, ServiceAttachmentSerializer,
    ServicePendencySerializer, ServiceTypeSerializer,
    ServicePaymentDocumentSerializer, ServiceObservationSerializer, ServiceStatusHistorySerializer,
    ExternalUserSerializer
)
from solar.documents.views import (
    AbstractDocumentListViewSet, AbstractPaymentDocumentView,
    AbstractDocumentDownloadView, AbstractDocumentDownloadAllView
)

from solar.users.models import UserChangeLog
from solar.users.serializers import UserSerializer
from solar.users.permissions import GeneralUserThrottle

# Integrando as notificações refatoradas em tempo real (WebSocket + E-mail)
from solar.notifications.services import (
    notificar_nova_solicitacao,
    notificar_mudanca_status,
    notificar_pendencia,
    notificar_boleto_anexado_servico,
    notificar_comprovante_anexado_servico,
    notificar_criacao_usuario_externo
)

from django.contrib.auth import get_user_model
logger = logging.getLogger(__name__)

User = get_user_model()

class IsAdminOrSuperuser(permissions.BasePermission):
    """Permite acesso apenas a superusuários ou usuários com is_admin=True."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_superuser or getattr(request.user, 'is_admin', False)))


class ExternalUserViewSet(viewsets.ModelViewSet):
    """
    CRUD completo para gerenciamento de Parceiros Externos.
    Acesso restrito a administradores.
    """
    serializer_class = ExternalUserSerializer
    permission_classes = [IsAdminOrSuperuser]
    throttle_classes = [GeneralUserThrottle]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        return User.objects.filter(is_externo=True).prefetch_related('tipos_servico').order_by('name')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        try:
            logger.info(f"Tentativa de criação de usuário externo: {request.data.get('email')} por {request.user.email}")
            
            # 1. Cria o usuário
            response = super().create(request, *args, **kwargs)
            logger.info(f"Usuário externo criado com sucesso: {request.data.get('email')}")
            
            # 2. Busca o utilizador no banco e captura a senha do payload
            user_criado = User.objects.get(email=request.data.get('email'))
            senha_provisoria = request.data.get('password')
            
            # 3. Dispara a notificação via WebSocket e o e-mail de boas-vindas
            notificar_criacao_usuario_externo(user_criado, senha_provisoria)
            
            return response
        except Exception as e:
            logger.error(f"Erro ao criar usuário externo: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Erro ao criar usuário externo', 'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        original_instance_values = {field: getattr(instance, field, None) for field in request.data.keys()}

        response = super().update(request, *args, **kwargs)

        if status.is_success(response.status_code):
            instance.refresh_from_db()
            
            # Reaproveitamento da lógica de auditoria da CustomUserViewSet
            fields_to_log_manually = ['name', 'celular', 'cpf', 'is_active', 'email']
            for field_name in request.data.keys():
                if field_name in fields_to_log_manually:
                    old_value = original_instance_values.get(field_name)
                    current_saved_value = getattr(instance, field_name, None)

                    old_val_str = str(old_value) if old_value is not None else ''
                    new_val_str = str(current_saved_value) if current_saved_value is not None else ''

                    if old_val_str != new_val_str:
                        try:
                            UserChangeLog.objects.create(
                                user=instance,
                                changed_by=request.user,
                                field_name=field_name,
                                old_value=old_val_str,
                                new_value=new_val_str
                            )
                        except Exception as log_exc:
                            logger.error(f"Erro ao registrar UserChangeLog: {log_exc}")

        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            logger.warning(f"Deletando usuário externo: {instance.email} por admin {request.user.email}")
            response = super().destroy(request, *args, **kwargs)
            return response
        except Exception as e:
            logger.error(f"Erro ao deletar usuário externo {instance.email}: {str(e)}")
            return Response(
                {'error': 'Erro ao deletar usuário externo'},
                status=status.HTTP_400_BAD_REQUEST
            )

class ServiceStatusHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Histórico de mudanças de status das solicitações de serviço.
    """
    serializer_class = ServiceStatusHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None # Remove a paginação para exibir o histórico completo na linha do tempo

    def get_queryset(self):
        service_pk = self.kwargs.get('service_pk')
        
        if getattr(self, "swagger_fake_view", False) or not service_pk:
            return ServiceStatusHistory.objects.none()

        service = get_object_or_404(ServiceRequest, pk=service_pk)
        return ServiceStatusHistory.objects.filter(service=service).order_by('-changed_at')
class ServiceRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet principal para solicitações de serviços.
    """
    serializer_class = ServiceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ServiceRequest.objects.none()

        user = self.request.user
        queryset = ServiceRequest.objects.select_related('tipo', 'solicitante', 'executor').prefetch_related('anexos', 'unidades').order_by('-created_at')

        if user.is_superuser or getattr(user, 'is_admin', False):
            return queryset
        elif getattr(user, 'is_externo', False):
            return queryset.filter(tipo__in=user.tipos_servico.all())
        else:
            return queryset.filter(solicitante=user)

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        
        # Bloqueio corrigido incluindo o técnico (P1-6)
        if getattr(user, 'is_externo', False) or getattr(user, 'is_admin', False) or getattr(user, 'is_tecnico', False) or user.is_superuser:
            raise PermissionDenied("Apenas clientes podem criar solicitações de serviço.")

        service_type = serializer.validated_data.get('tipo')
        valor = service_type.valor if service_type else 0

        # O solicitante é fixado como o usuário logado
        service = serializer.save(solicitante=user, valor_cobrado=valor)

        # Dispara notificação WebSocket para os usuários externos habilitados
        notificar_nova_solicitacao(service)

    @action(detail=True, methods=['post'], url_path='status')
    @transaction.atomic
    def alterar_status(self, request, pk=None):
        """
        Transição controlada de status com registro de histórico, notificação WebSocket
        e gravação de campos de resultado.
        """
        service = self.get_object()
        user = request.user
        
        # RF-03: Apenas admin e externos com permissão no tipo podem mudar status
        is_admin_or_super = user.is_superuser or getattr(user, 'is_admin', False)
        is_externo_autorizado = getattr(user, 'is_externo', False) and service.tipo in user.tipos_servico.all()

        if not (is_admin_or_super or is_externo_autorizado):
            raise PermissionDenied("Você não tem permissão para alterar o status desta solicitação.")

        novo_status = request.data.get('status')
        status_antigo = service.status

        # 1. Validação de integridade do Status
        if novo_status not in [c[0] for c in ServiceRequest.StatusChoices.choices]:
            raise ValidationError({'status': 'Status inválido ou não informado.'})

        # 2. Regra de Negócio: Reprovação exige motivo
        motivo_reprova = request.data.get('motivo_reprova')
        if novo_status == ServiceRequest.StatusChoices.REPROVADO and not motivo_reprova:
            raise ValidationError({'motivo_reprova': 'É obrigatório fornecer o motivo da reprovação.'})

        # 3. Aplica o Status e Motivo base
        service.status = novo_status
        if motivo_reprova:
            service.motivo_reprova = motivo_reprova

        # 4. Regra de Negócio: Define o executor quando entra em realização (P1-7)
        if novo_status == ServiceRequest.StatusChoices.REALIZANDO and not service.executor:
            service.executor = user

        # 5. Regra de Negócio: Recolha de campos de resultado na Conclusão (P1-7)
        if novo_status in [ServiceRequest.StatusChoices.CONCLUIDO, ServiceRequest.StatusChoices.SERVICO_SOLICITADO]:
            # Grava os campos que vierem no request (se existirem, caso contrário mantém os originais)
            service.protocolo = request.data.get('protocolo', service.protocolo)
            service.uc_resultado = request.data.get('uc_resultado', service.uc_resultado)
            
            # Formata a data se for enviada
            prazo = request.data.get('prazo_concessionaria')
            if prazo:
                service.prazo_concessionaria = prazo
                
            service.nota = request.data.get('nota', service.nota)
            service.carga = request.data.get('carga', service.carga)
            service.tensao_nominal = request.data.get('tensao_nominal', service.tensao_nominal)
            service.potencia_transformador = request.data.get('potencia_transformador', service.potencia_transformador)

        service.save()

        # Registro no histórico (Apenas se o status realmente mudou)
        if status_antigo != novo_status:
            ServiceStatusHistory.objects.create(
                service=service,
                changed_by=user,
                old_status=status_antigo,
                new_status=novo_status
            )
            # Disparo da notificação em tempo real via WebSocket
            notificar_mudanca_status(service)

        return Response(self.get_serializer(service).data, status=status.HTTP_200_OK)

class ServiceTypeViewSet(viewsets.ModelViewSet):
    """
    Gestão do Catálogo de Tipos de Serviço (Tabela de Preços e Prazos).
    """
    serializer_class = ServiceTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # Desativa a paginação para devolver a lista completa para o frontend de uma vez

    def get_queryset(self):
        """
        Admins vêm tudo (para poderem reativar inativos).
        Clientes e Externos só veem serviços ativos.
        """
        if getattr(self, "swagger_fake_view", False):
            return ServiceType.objects.none()

        user = self.request.user
        
        # Apenas superusers e administradores veem todos os registos
        if user.is_superuser or getattr(user, 'is_admin', False):
            return ServiceType.objects.all().order_by('nome')
            
        # O resto do sistema (Clientes, Externos, Técnicos) só vê os que estão disponíveis
        return ServiceType.objects.filter(ativo=True).order_by('nome')

    def _check_admin_write_permission(self):
        """Helper para bloquear escrita a não-administradores."""
        user = self.request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False)):
            raise PermissionDenied("Acesso restrito: Apenas administradores podem criar ou alterar os Tipos de Serviço.")

    def perform_create(self, serializer):
        self._check_admin_write_permission()
        serializer.save()

    def perform_update(self, serializer):
        self._check_admin_write_permission()
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """
        Bloqueia a exclusão física do banco de dados (DELETE) para não quebrar
        solicitações antigas que dependem do ServiceType.
        """
        raise PermissionDenied(
            "A exclusão de tipos de serviço é bloqueada por segurança. "
            "Para retirar um serviço de circulação, edite-o e altere o campo 'ativo' para falso."
        )

class ServiceAttachmentViewSet(AbstractDocumentListViewSet):
    """
    Gerenciador de anexos do serviço (Upload, Aprovação e Substituição).
    """
    model = ServiceAttachment
    parent_model = ServiceRequest
    parent_url_kwarg = 'service_pk'
    parent_relation_field = 'service'
    serializer_class = ServiceAttachmentSerializer

    def check_read_permission(self, service):
        user = self.request.user
        is_admin_or_super = user.is_superuser or getattr(user, 'is_admin', False)
        is_externo_autorizado = getattr(user, 'is_externo', False) and service.tipo in user.tipos_servico.all()
        is_dono = (user == service.solicitante)

        if not (is_admin_or_super or is_externo_autorizado or is_dono):
            raise PermissionDenied("Acesso negado a este serviço.")

    @transaction.atomic
    def perform_create(self, serializer):
        service = self.get_parent_object()
        self.check_read_permission(service)

        documento = serializer.save(service=service, enviado_por=self.request.user)
        user_request = self.request.user

        # Notificações e atalhos operacionais baseados na categoria do anexo
        if documento.categoria == ServiceAttachment.CategoriaChoices.BOLETO:
            notificar_boleto_anexado_servico(service)

        elif documento.categoria == ServiceAttachment.CategoriaChoices.COMPROVANTE:
            notificar_comprovante_anexado_servico(service)
            service.payment_status = 'COMPROVANTE_EM_ANALISE'
            service.save(update_fields=['payment_status'])

        elif documento.categoria == ServiceAttachment.CategoriaChoices.PENDENCIA_CLIENTE and documento.pendencia:
            documento.pendencia.status = 'RESPONDIDA'
            documento.pendencia.save(update_fields=['status'])

    @transaction.atomic
    def perform_update(self, serializer):
        if getattr(self.request.user, 'is_cliente', False):
            raise PermissionDenied("Não é possível alterar a solicitação após o envio.")
        serializer.save()

    def perform_destroy(self, instance):
        if getattr(self.request.user, 'is_cliente', False):
            raise PermissionDenied("Clientes não podem apagar solicitações.")
        instance.delete()

class ServicePendencyViewSet(viewsets.ModelViewSet):
    """
    Gerenciamento de pendências nomeadas abertas pela equipe.
    """
    serializer_class = ServicePendencySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Adicionar filtro de segurança, atualmente qualquer pessoa pode ver pendências alheias
        service_pk = self.kwargs.get('service_pk')
        if getattr(self, "swagger_fake_view", False) or not service_pk:
            return ServicePendency.objects.none()

        service = get_object_or_404(ServiceRequest, pk=service_pk)
        
        # Bloquear cliente se a solicitação não for dele
        user = self.request.user
        if getattr(user, 'is_cliente', False) and service.solicitante != user:
            return ServicePendency.objects.none()

        return ServicePendency.objects.filter(service=service).order_by('-created_at')

    def perform_update(self, serializer):
        if getattr(self.request.user, 'is_cliente', False):
            raise PermissionDenied("Clientes não podem alterar o estado das pendências.")
        serializer.save()

    def perform_destroy(self, instance):
        if getattr(self.request.user, 'is_cliente', False):
            raise PermissionDenied("Clientes não podem apagar pendências.")
        instance.delete()

    @transaction.atomic
    def perform_create(self, serializer):
        service_pk = self.kwargs.get('service_pk')
        service = get_object_or_404(ServiceRequest, pk=service_pk)
        user = self.request.user

        if getattr(user, 'is_cliente', False):
            raise PermissionDenied("Apenas administradores e executores externos podem abrir pendências.")

        pendencia = serializer.save(service=service, criada_por=user, status='ABERTA')

        # Atualiza a solicitação para o status PENDENCIAS se necessário
        if service.status != 'PENDENCIAS':
            service.status = 'PENDENCIAS'
            service.save(update_fields=['status'])

        # Dispara notificação no sino e WebSocket do cliente
        notificar_pendencia(service, pendencia.titulo)

class ServicePaymentDocumentView(AbstractPaymentDocumentView):
    model = ServiceAttachment
    parent_model = ServiceRequest
    parent_url_kwarg = 'parent_pk'
    parent_relation_field = 'service'
    serializer_class = ServicePaymentDocumentSerializer

    def check_access_permission(self, service):
        user = self.request.user
        if getattr(user, 'is_cliente', False) and service.solicitante != user:
            raise PermissionDenied("Acesso negado.")

class ServiceAttachmentDownloadView(AbstractDocumentDownloadView):
    model = ServiceAttachment
    parent_model = ServiceRequest
    parent_url_kwarg = 'parent_pk'
    document_url_kwarg = 'document_pk'

    def check_download_permission(self, request, service, document):
        user = request.user
        is_equipe = user.is_superuser or getattr(user, 'is_admin', False) or (getattr(user, 'is_externo', False) and service.tipo in user.tipos_servico.all())
        is_dono = (user == service.solicitante)

        if not (is_equipe or is_dono):
            raise PermissionDenied("Sem permissão para download.")


class ServiceObservationViewSet(viewsets.ModelViewSet):
    """
    Gerenciamento de observações livres feitas pela equipe e executores externos.
    """
    serializer_class = ServiceObservationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        service_pk = self.kwargs.get('service_pk')
        if getattr(self, "swagger_fake_view", False) or not service_pk:
            return ServiceObservation.objects.none()

        service = get_object_or_404(ServiceRequest, pk=service_pk)
        return ServiceObservation.objects.filter(service=service).order_by('-created_at')

    @transaction.atomic
    def perform_create(self, serializer):
        service_pk = self.kwargs.get('service_pk')
        service = get_object_or_404(ServiceRequest, pk=service_pk)
        user = self.request.user

        if getattr(user, 'is_cliente', False):
            raise PermissionDenied("Apenas administradores e executores externos podem adicionar observações.")

        serializer.save(service=service, criada_por=user)
class ServiceAttachmentDownloadAllView(AbstractDocumentDownloadAllView):
    model = ServiceAttachment
    parent_model = ServiceRequest
    parent_relation_field = 'service'
    parent_url_kwarg = 'parent_pk'

    def check_download_all_permission(self, request, service):
        user = request.user
        is_equipe = user.is_superuser or getattr(user, 'is_admin', False) or (getattr(user, 'is_externo', False) and service.tipo in user.tipos_servico.all())
        is_dono = (user == service.solicitante)

        if not (is_equipe or is_dono):
            raise PermissionDenied("Sem permissão para baixar os anexos.")