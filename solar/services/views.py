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
    ServiceObservation, ServiceStatusHistory
)
from solar.services.serializers import (
    ServiceRequestSerializer, ServiceAttachmentSerializer,
    ServicePendencySerializer, ServiceObservationSerializer,
    ServicePaymentDocumentSerializer
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
        
        # RF-06: Apenas o cliente pode abrir solicitações
        if getattr(user, 'is_externo', False) or getattr(user, 'is_admin', False) or user.is_superuser:
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
    parent_relation_field = 'service'
    serializer_class = ServicePaymentDocumentSerializer

    def check_access_permission(self, service):
        user = self.request.user
        if getattr(user, 'is_cliente', False) and service.solicitante != user:
            raise PermissionDenied("Acesso negado.")


class ServiceAttachmentDownloadView(AbstractDocumentDownloadView):
    model = ServiceAttachment
    parent_model = ServiceRequest

    def check_download_permission(self, request, service, document):
        user = request.user
        is_equipe = user.is_superuser or getattr(user, 'is_admin', False) or (getattr(user, 'is_externo', False) and service.tipo in user.tipos_servico.all())
        is_dono = (user == service.solicitante)

        if not (is_equipe or is_dono):
            raise PermissionDenied("Sem permissão para download.")


class ServiceAttachmentDownloadAllView(AbstractDocumentDownloadAllView):
    model = ServiceAttachment
    parent_model = ServiceRequest
    parent_relation_field = 'service'

    def check_download_all_permission(self, request, service):
        user = request.user
        is_equipe = user.is_superuser or getattr(user, 'is_admin', False) or (getattr(user, 'is_externo', False) and service.tipo in user.tipos_servico.all())
        is_dono = (user == service.solicitante)

        if not (is_equipe or is_dono):
            raise PermissionDenied("Sem permissão para baixar os anexos.")