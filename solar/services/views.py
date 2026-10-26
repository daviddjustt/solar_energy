import os
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

# Integrando as notificações refatoradas em tempo real (WebSocket + E-mail)
from solar.notifications.services import (
    notificar_nova_solicitacao,
    notificar_mudanca_status,
    notificar_pendencia,
    notificar_documento_rejeitado_servico,
    notificar_boleto_anexado_servico,
    notificar_comprovante_anexado_servico
)

from django.contrib.auth import get_user_model
User = get_user_model()
class ExternalUserViewSet(viewsets.ModelViewSet):
    """
    CRUD de Usuários Externos (Exclusivo Admin). RF-05.
    """
    serializer_class = ExternalUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        return User.objects.filter(is_externo=True)

    def check_permissions(self, request):
        super().check_permissions(request)
        if not (request.user.is_superuser or getattr(request.user, 'is_admin', False)):
            raise PermissionDenied("Acesso exclusivo a administradores.")

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        
        # Bloqueio corrigido incluindo o técnico (P1-6)
        if getattr(user, 'is_externo', False) or getattr(user, 'is_admin', False) or getattr(user, 'is_tecnico', False) or user.is_superuser:
            raise PermissionDenied("Apenas clientes podem criar solicitações de serviço.")

    # Bloqueio para evitar que o cliente edite ou apague a solicitação (P1-8)
    def perform_update(self, serializer):
        user = self.request.user
        is_equipe = user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_externo', False)
        if not is_equipe:
            raise PermissionDenied("Clientes não podem editar dados após o envio.")
        serializer.save()

    def perform_destroy(self, instance):
        if not (self.request.user.is_superuser or getattr(self.request.user, 'is_admin', False)):
            raise PermissionDenied("Apenas administradores podem apagar solicitações.")
        instance.delete()

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
        Transição controlada de status com registro de histórico e notificação WebSocket.
        """
        service = self.get_object()
        user = request.user
        
        # RF-03: Apenas admin e externos com permissão no tipo podem mudar status
        is_admin_or_super = user.is_superuser or getattr(user, 'is_admin', False)
        is_externo_autorizado = getattr(user, 'is_externo', False) and service.tipo in user.tipos_servico.all()

        if not (is_admin_or_super or is_externo_autorizado):
            raise PermissionDenied("Você não tem permissão para alterar o status desta solicitação.")

        novo_status = request.data.get('status')
        motivo_reprova = request.data.get('motivo_reprova')
        status_antigo = service.status

        if novo_status == 'REPROVADO' and not motivo_reprova:
            raise ValidationError({'motivo_reprova': 'É obrigatório fornecer o motivo da reprovação.'})

        service.status = novo_status
        if motivo_reprova:
            service.motivo_reprova = motivo_reprova

        # Se for para 'REALIZANDO', registra o executor
        if novo_status == 'REALIZANDO' and not service.executor:
            service.executor = user

        service.save()

        # Registro no histórico
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
        instance = self.get_object()
        service = instance.service
        user_request = self.request.user

        self.check_read_permission(service)
        novo_status = serializer.validated_data.get('status', instance.status)

        # Se for reenvio feito pelo cliente
        if getattr(user_request, 'is_cliente', False):
            if 'arquivo' in serializer.validated_data:
                updated_instance = serializer.save(status=ServiceAttachment.STATUS_IN_ANALYSIS)
            else:
                updated_instance = serializer.save()
        else:
            # Equipe / Admin alterando o status da análise do documento
            if novo_status == ServiceAttachment.STATUS_APPROVED:
                updated_instance = serializer.save(approved_at=timezone.now())
                if instance.categoria == ServiceAttachment.CategoriaChoices.COMPROVANTE:
                    service.payment_status = 'PAGO'
                    service.save(update_fields=['payment_status'])

            elif novo_status == ServiceAttachment.STATUS_REJECTED:
                motivo = serializer.validated_data.get('rejection_reason')
                if not motivo:
                    raise ValidationError({'rejection_reason': 'O motivo da rejeição é obrigatório.'})

                updated_instance = serializer.save()
                if instance.categoria == ServiceAttachment.CategoriaChoices.COMPROVANTE:
                    service.payment_status = 'PENDENTE'
                    service.save(update_fields=['payment_status'])

                # Notifica o cliente via WebSocket sobre a rejeição
                notificar_documento_rejeitado_servico(
                    service=service,
                    nome_documento=updated_instance.document_name or updated_instance.get_categoria_display(),
                    motivo=motivo
                )
            else:
                updated_instance = serializer.save()

    def perform_destroy(self, instance):
        if getattr(self.request.user, 'is_cliente', False):
            raise PermissionDenied("Clientes não podem remover anexos do sistema.")
        instance.delete()

class ServicePendencyViewSet(viewsets.ModelViewSet):
    """
    Gerenciamento de pendências nomeadas abertas pela equipe.
    """
    serializer_class = ServicePendencySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        service_pk = self.kwargs.get('service_pk')
        if getattr(self, "swagger_fake_view", False) or not service_pk:
            return ServicePendency.objects.none()

        service = get_object_or_404(ServiceRequest, pk=service_pk)
        return ServicePendency.objects.filter(service=service).order_by('-created_at')

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