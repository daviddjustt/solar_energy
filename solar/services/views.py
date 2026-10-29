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
    notificar_criacao_usuario_externo,
    notificar_documento_rejeitado_servico,
)


from django.contrib.auth import get_user_model
logger = logging.getLogger(__name__)

User = get_user_model()


class ServiceAccessMixin:
    """
    Mixin para centralizar a lógica de permissão baseada em escopo de serviços.
    Pode ser herdado por qualquer ViewSet do módulo de serviços.
    """
    def check_access_permission(self, service):
        user = self.request.user

        # 1. Bloqueia usuários não autenticados por segurança
        if not user or not user.is_authenticated:
            raise PermissionDenied("Autenticação necessária.")

        # 2. Se o usuário for o dono (cliente que solicitou o serviço)
        if service.solicitante == user:
            return

        # 3. Se o usuário for Administrador ou Superuser
        if user.is_superuser or getattr(user, 'is_admin', False):
            return

        # 4. Se o usuário for Externo, valida se o Tipo de Serviço está liberado para ele
        if getattr(user, 'is_externo', False):
            # O prefetch_related ou acesso direto ao M2M já resolve isso
            if service.tipo in user.tipos_servico.all():
                return

        # 5. Fallback: Acesso negado
        raise PermissionDenied("Acesso negado a este serviço.")
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

# Adicionamos ServiceAccessMixin como primeira herança
class ServiceStatusHistoryViewSet(ServiceAccessMixin, viewsets.ReadOnlyModelViewSet):
    """
    Histórico de mudanças de status das solicitações de serviço.
    """
    serializer_class = ServiceStatusHistorySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        service_pk = self.kwargs.get('service_pk')
        
        if getattr(self, "swagger_fake_view", False) or not service_pk:
            return ServiceStatusHistory.objects.none()

        service = get_object_or_404(ServiceRequest, pk=service_pk)
        
        # Chama a validação centralizada do Mixin (Resolve o R6)
        self.check_access_permission(service)

        return ServiceStatusHistory.objects.filter(service=service).order_by('-changed_at')

class ServiceRequestViewSet(ServiceAccessMixin, viewsets.ModelViewSet):
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
    def perform_update(self, serializer):
        instance = self.get_object()
        user = self.request.user

        # --- CORREÇÃO P1-8 e R4: Deteção forte de cliente ---
        is_cliente = getattr(user, 'is_cliente', False) and not (
            user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_externo', False)
        )

        # Regra de Negócio (Seção 5): Cliente não edita dados após o envio.
        if is_cliente:
            raise PermissionDenied("Clientes não podem alterar os dados da solicitação após a sua criação.")

        # --- CORREÇÃO P1-8: Proteger campos de resultado ---
        # Garantimos que estes campos NUNCA são editados por PATCH direto. 
        # A equipe é obrigada a usar a ação de 'status' (alterar_status) para os preencher.
        campos_resultado_protegidos = [
            'protocolo', 'uc_resultado', 'prazo_concessionaria', 
            'nota', 'carga', 'tensao_nominal', 'potencia_transformador', 'executor'
        ]
        for campo in campos_resultado_protegidos:
            serializer.validated_data.pop(campo, None)

        # --- CORREÇÃO P1-8: Recálculo do valor cobrado ---
        # Se a equipe alterar o Tipo de Serviço, o sistema ajusta o valor cobrado
        novo_tipo = serializer.validated_data.get('tipo')
        if novo_tipo and novo_tipo != instance.tipo:
            serializer.validated_data['valor_cobrado'] = novo_tipo.valor

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        
        # --- CORREÇÃO P1-8: DELETE restrito ao Admin ---
        is_admin = user.is_superuser or getattr(user, 'is_admin', False)
        
        if not is_admin:
            raise PermissionDenied("Apenas administradores podem excluir uma solicitação de serviço.")
            
        instance.delete()

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
        service = self.get_object()
        
        # --- CORREÇÃO P1-7: Uso do Mixin centralizado de permissão ---
        self.check_access_permission(service)
        
        user = request.user
        novo_status = request.data.get('status')
        
        # --- CORREÇÃO P1-7: SERVICO_SOLICITADO como status final/bloqueado ---
        status_finais = [
            ServiceRequest.StatusChoices.CONCLUIDO, 
            ServiceRequest.StatusChoices.REPROVADO,
            ServiceRequest.StatusChoices.SERVICO_SOLICITADO
        ]
        
        if service.status in status_finais:
            return Response(
                {"detail": f"Esta solicitação já se encontra encerrada ({service.get_status_display()}) e não pode mais sofrer alterações de status."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validação do motivo de reprovação (obrigatório se for reprovado)
        if novo_status == ServiceRequest.StatusChoices.REPROVADO:
            motivo = request.data.get('motivo_reprova')
            if not motivo:
                return Response(
                    {"motivo_reprova": "O motivo da reprovação é obrigatório para encerrar a solicitação."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            service.motivo_reprova = motivo

        # --- CORREÇÃO P1-7: Exigência de campos por destino / tipo de serviço ---
        if novo_status == ServiceRequest.StatusChoices.CONCLUIDO:
            tipo_codigo = service.tipo.codigo if service.tipo else ""
            
            # Validações específicas para Consulta de Carga
            if tipo_codigo == 'consulta_carga':
                carga = request.data.get('carga')
                tensao = request.data.get('tensao_nominal')
                transformador = request.data.get('potencia_transformador')
                
                erros = {}
                if carga is None: erros['carga'] = "A carga é obrigatória para concluir a consulta."
                if not tensao: erros['tensao_nominal'] = "A tensão nominal é obrigatória."
                if transformador is None: erros['potencia_transformador'] = "A potência do transformador é obrigatória."
                if erros:
                    return Response(erros, status=status.HTTP_400_BAD_REQUEST)
                    
            # Validações gerais para serviços comuns de concessionária
            elif tipo_codigo in ['ligacao_nova', 'alteracao_carga_fase', 'alteracao_carga', 'troca_titularidade']:
                protocolo = request.data.get('protocolo')
                uc_resultado = request.data.get('uc_resultado')
                
                if not protocolo and tipo_codigo != 'troca_titularidade':
                    return Response({"protocolo": "O número do protocolo da concessionária é obrigatório para a conclusão."}, status=status.HTTP_400_BAD_REQUEST)

        # Atribuição dos campos de resultado enviados no request
        campos_resultado = [
            'protocolo', 'uc_resultado', 'prazo_concessionaria', 
            'nota', 'carga', 'tensao_nominal', 'potencia_transformador', 'executor'
        ]
        for campo in campos_resultado:
            if campo in request.data:
                setattr(service, campo, request.data.get(campo))

        status_antigo = service.status
        service.status = novo_status
        service.save()

        # Registra no histórico de status
        ServiceStatusHistory.objects.create(
            service=service,
            changed_by=user,
            old_status=status_antigo,
            new_status=novo_status
        )

        # Dispara as notificações de mudança de status
        notificar_mudanca_status(service)

        return Response({"status": f"Status alterado para {service.get_status_display()} com sucesso."}, status=status.HTTP_200_OK)
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

class ServiceAttachmentViewSet(ServiceAccessMixin,AbstractDocumentListViewSet):
    """
    Gerenciador de anexos do serviço (Upload, Aprovação e Substituição).
    """
    model = ServiceAttachment
    parent_model = ServiceRequest
    parent_url_kwarg = 'service_pk'
    parent_relation_field = 'service'
    serializer_class = ServiceAttachmentSerializer


    @transaction.atomic
    def perform_create(self, serializer):
        service = self.get_parent_object()
        self.check_access_permission(service)
        user_request = self.request.user

        categoria = serializer.validated_data.get('categoria')
        related_boleto = serializer.validated_data.get('related_payment_document')

        # --- REGRA R9: Validação extra de Comprovante e Boleto ---
        if categoria == ServiceAttachment.CategoriaChoices.COMPROVANTE and related_boleto:
            # Impede anexar comprovante se o boleto já foi pago/aprovado
            if related_boleto.status == ServiceAttachment.STATUS_APPROVED:
                raise ValidationError({'related_payment_document': 'Este boleto já consta como pago e aprovado.'})

        # --- CORREÇÃO R4 e R3b: Detecção Forte de Cliente ---
        # Garante que um externo/admin com is_cliente=True não sofra as travas do cliente
        is_cliente = getattr(user_request, 'is_cliente', False) and not (
            user_request.is_superuser or 
            getattr(user_request, 'is_admin', False) or 
            getattr(user_request, 'is_externo', False)
        )

        if is_cliente:
            # Trava o status inicial e limpa motivos antigos forçadamente
            documento = serializer.save(
                service=service, 
                enviado_por=user_request,
                status=ServiceAttachment.STATUS_IN_ANALYSIS,
                rejection_reason=None
            )
        else:
            documento = serializer.save(service=service, enviado_por=user_request)

        # --- CORREÇÃO R4: Preencher ServiceUnit.fatura ---
        if documento.unidade:
            unidade = documento.unidade
            unidade.fatura = documento
            unidade.save(update_fields=['fatura'])
        else: 
            # Apenas loga se o logger estiver devidamente importado no topo do arquivo
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Anexo {documento.id} criado sem unidade associada para o serviço {service.id}.")

        # --- Notificações e atalhos operacionais ---
        if documento.categoria == ServiceAttachment.CategoriaChoices.BOLETO:
            notificar_boleto_anexado_servico(service)

        elif documento.categoria == ServiceAttachment.CategoriaChoices.COMPROVANTE:
            notificar_comprovante_anexado_servico(service)
            if service.payment_status != 'COMPROVANTE_EM_ANALISE':
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

        self.check_access_permission(service)
        
        # --- CORREÇÃO R4: Detecção forte de cliente ---
        # Evita que um Admin/Externo com is_cliente=True caia nas regras do cliente
        is_cliente = getattr(user_request, 'is_cliente', False) and not (
            user_request.is_superuser or 
            getattr(user_request, 'is_admin', False) or 
            getattr(user_request, 'is_externo', False)
        )

        if is_cliente:
            # Removemos da requisição qualquer tentativa de mudar status ou motivo
            serializer.validated_data.pop('status', None)
            serializer.validated_data.pop('rejection_reason', None)
            
            if 'arquivo' in serializer.validated_data:
                # Cliente atualiza arquivo = Volta pra análise forçadamente e limpa motivo
                updated_instance = serializer.save(
                    status=ServiceAttachment.STATUS_IN_ANALYSIS,
                    rejection_reason=None
                )
                
                # --- CORREÇÃO R4: Pagamento no reenvio ---
                # Se for comprovante, volta o status do pagamento para análise
                if updated_instance.categoria == ServiceAttachment.CategoriaChoices.COMPROVANTE:
                    service.payment_status = 'COMPROVANTE_EM_ANALISE'
                    service.save(update_fields=['payment_status'])
                
                # --- CORREÇÃO R4: Notificar o reenvio ---
                # Dispara notificação para a equipe informando que o cliente reenviou o arquivo
                # (Assumindo que você crie/tenha esta função no notifications/services.py)
                try:
                    from solar.notifications.services import notificar_documento_reenviado_servico
                    notificar_documento_reenviado_servico(service, updated_instance.document_name or updated_instance.get_categoria_display())
                except ImportError:
                    pass # Caso a notificação ainda não tenha sido implementada
            else:
                updated_instance = serializer.save()
        else:
            novo_status = serializer.validated_data.get('status', instance.status)
            
            if novo_status == ServiceAttachment.STATUS_APPROVED:
                # --- CORREÇÃO R4: Limpeza do motivo antigo ---
                # Garante que o rejection_reason fique None ao aprovar
                updated_instance = serializer.save(
                    approved_at=timezone.now(),
                    rejection_reason=None
                )
                
                # Se aprovou comprovante, finaliza o pagamento do serviço
                if instance.categoria == ServiceAttachment.CategoriaChoices.COMPROVANTE:
                    service.payment_status = 'PAGO'
                    service.save(update_fields=['payment_status'])
                    
            elif novo_status == ServiceAttachment.STATUS_REJECTED:
                motivo = serializer.validated_data.get('rejection_reason')
                if not motivo:
                    raise ValidationError({'rejection_reason': 'O motivo da rejeição é obrigatório.'})
                
                updated_instance = serializer.save()
                
                # Se rejeitou comprovante, volta pagamento para pendente
                if instance.categoria == ServiceAttachment.CategoriaChoices.COMPROVANTE:
                    service.payment_status = 'PENDENTE'
                    service.save(update_fields=['payment_status'])
                
                notificar_documento_rejeitado_servico(
                    service, 
                    updated_instance.document_name or updated_instance.get_categoria_display(), 
                    motivo
                )
            else:
                updated_instance = serializer.save()
            
    @transaction.atomic
    def perform_destroy(self, instance):
        service = instance.service
        user = self.request.user
        
        self.check_access_permission(service)

        # --- CORREÇÃO R4: Deteção forte de cliente ---
        is_cliente = getattr(user, 'is_cliente', False) and not (
            user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_externo', False)
        )

        if is_cliente:
            # Clientes só podem apagar aquilo que ainda está em análise
            if instance.status != ServiceAttachment.STATUS_IN_ANALYSIS:
                raise PermissionDenied("Clientes só podem apagar documentos que ainda estão Em Análise.")
                
        instance.delete()

class ServicePendencyViewSet(ServiceAccessMixin, viewsets.ModelViewSet):
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
        
        # Filtra o acesso utilizando o Mixin (R6)
        try:
            self.check_access_permission(service)
        except PermissionDenied:
            return ServicePendency.objects.none()

        return ServicePendency.objects.filter(service=service).order_by('-created_at')

    @transaction.atomic
    def perform_create(self, serializer):
        service_pk = self.kwargs.get('service_pk')
        service = get_object_or_404(ServiceRequest, pk=service_pk)
        user = self.request.user

        # 1. Validação de segurança: Apenas equipe/admin cria
        is_equipe = user.is_superuser or getattr(user, 'is_admin', False) or (getattr(user, 'is_externo', False) and service.tipo in user.tipos_servico.all())
        if not is_equipe:
            raise PermissionDenied("Acesso negado. Apenas a equipe técnica pode abrir pendências.")

        # --- REGRA R5: Bloqueia abertura em serviços finalizados/solicitados ---
        status_finais = [
            ServiceRequest.StatusChoices.CONCLUIDO, 
            ServiceRequest.StatusChoices.REPROVADO,
            ServiceRequest.StatusChoices.SERVICO_SOLICITADO
        ]
        
        if service.status in status_finais:
            raise ValidationError(
                {"detail": f"Não é possível abrir pendências. Este serviço já encontra-se '{service.get_status_display()}'."}
            )
        
        # 3. Cria a pendência
        pendencia = serializer.save(service=service, criada_por=user, status='ABERTA')

        # 4. Altera o status do serviço para PENDENCIAS de forma segura
        if service.status != 'PENDENCIAS':
            status_antigo = service.status
            service.status = 'PENDENCIAS'
            service.save(update_fields=['status'])
            
            ServiceStatusHistory.objects.create(
                service=service, 
                changed_by=user, 
                old_status=status_antigo, 
                new_status='PENDENCIAS'
            )

        notificar_pendencia(service, pendencia.titulo)

    def perform_destroy(self, instance):
        # Apenas admins excluem pendências
        if not (self.request.user.is_superuser or getattr(self.request.user, 'is_admin', False)):
            raise PermissionDenied("Apenas administradores podem apagar pendências.")
        instance.delete()

    @transaction.atomic
    def perform_update(self, serializer):
        instance = self.get_object()
        service = instance.service
        user = self.request.user
        
        self.check_access_permission(service)

        # --- REGRA R4: Deteção forte de cliente ---
        is_cliente = getattr(user, 'is_cliente', False) and not (
            user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_externo', False)
        )

        if is_cliente:
            # Clientes só podem alterar o status para RESPONDIDA
            novo_status = serializer.validated_data.get('status')
            if novo_status and novo_status != 'RESPONDIDA':
                raise PermissionDenied("Clientes só podem alterar o status para RESPONDIDA.")
            
            # Removemos qualquer tentativa maliciosa de mudar o título ou a observação original
            serializer.validated_data.pop('titulo', None)
            serializer.validated_data.pop('observacao', None)

        serializer.save()
class ServicePaymentDocumentView(ServiceAccessMixin, AbstractPaymentDocumentView):
    model = ServiceAttachment
    parent_model = ServiceRequest
    parent_url_kwarg = 'parent_pk'
    parent_relation_field = 'service'
    serializer_class = ServicePaymentDocumentSerializer

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


class ServiceObservationViewSet(ServiceAccessMixin, viewsets.ModelViewSet):
    """
    Gerenciamento de observações livres da equipe.
    Restrito apenas para leitura (GET) e criação (POST).
    """
    serializer_class = ServiceObservationSerializer
    permission_classes = [permissions.IsAuthenticated]

    # --- CORREÇÃO P1-9: Bloqueio de PATCH e DELETE ---
    http_method_names = ['get', 'post']
    # ------------------------------------------------

    def get_queryset(self):
        service_pk = self.kwargs.get('service_pk')
        if getattr(self, "swagger_fake_view", False) or not service_pk:
            return ServiceObservation.objects.none()

        service = get_object_or_404(ServiceRequest, pk=service_pk)
        
        try:
            self.check_access_permission(service)
        except PermissionDenied:
            return ServiceObservation.objects.none()

        return ServiceObservation.objects.filter(service=service).order_by('-created_at')

    @transaction.atomic
    def perform_create(self, serializer):
        service_pk = self.kwargs.get('service_pk')
        service = get_object_or_404(ServiceRequest, pk=service_pk)
        user = self.request.user

        self.check_access_permission(service)

        # Regra de Segurança: Apenas a equipa cria observações
        is_equipe = user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_externo', False)
        if not is_equipe:
            raise PermissionDenied("Apenas a equipe técnica pode adicionar observações.")

        serializer.save(service=service, autor=user)

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