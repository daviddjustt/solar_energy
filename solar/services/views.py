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
    ServiceRequest, 
    ServiceAttachment, 
    ServicePendency, 
    ServiceObservation, 
    ServiceStatusHistory, 
    ServiceType
)
from solar.services.serializers import (
    ServiceRequestSerializer, 
    ServiceAttachmentSerializer,
    ServicePendencySerializer, 
    ServiceTypeSerializer,
    ServicePaymentDocumentSerializer, 
    ServiceObservationSerializer, 
    ServiceStatusHistorySerializer,
    ExternalUserSerializer
)
from solar.documents.views import (
    AbstractDocumentListViewSet, 
    AbstractPaymentDocumentView,
    AbstractDocumentDownloadView, 
    AbstractDocumentDownloadAllView
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

    def check_team_permission(self, request, service):
        """
        Garante que apenas a equipe (Admin ou Externo do tipo) acesse a ação.
        Diferente do check_access_permission, este método BLOQUEIA o cliente.
        """
        is_admin = request.user.is_superuser or getattr(request.user, 'is_admin', False)
        is_externo_valido = getattr(request.user, 'is_externo', False) and service.tipo in request.user.tipos_servico.all()
        
        if not (is_admin or is_externo_valido):
            raise PermissionDenied("Apenas administradores e técnicos responsáveis têm permissão para esta ação.")
        
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
        logger.info(f"Tentativa de criação de usuário externo: {request.data.get('email')} por {request.user.email}")
        
        serializer = self.get_serializer(data=request.data)
        
        # --- CORREÇÃO P2-19: Formatação de erros preservada ---
        # O raise_exception=True devolve automaticamente o erro 400 formatado 
        # por campo para o frontend, dispensando o bloco try/except genérico.
        serializer.is_valid(raise_exception=True) 
        
        # 1. Cria o utilizador (e a senha auto-gerada, se necessário, dentro do serializer)
        user_criado = serializer.save()
        logger.info(f"Usuário externo criado com sucesso: {user_criado.email}")
        
        # 2. Captura a senha correta (digitada ou a auto-gerada que injetámos no objeto)
        senha_provisoria = getattr(user_criado, 'senha_provisoria_gerada', None)
        
        # 3. Dispara a notificação via WebSocket e o e-mail de boas-vindas
        notificar_criacao_usuario_externo(user_criado, senha_provisoria)
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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

    @staticmethod
    def validar_novo_status(novo_status):
        """
        Valida se o status fornecido existe na classe de choices do ServiceRequest.
        Lança um erro 400 automático (ValidationError) caso seja inválido.
        """
        status_validos = [choice[0] for choice in ServiceRequest.StatusChoices.choices]
        
        if not novo_status or novo_status not in status_validos:
            raise ValidationError({
                "status": f"Status inválido ou não informado. Escolhas permitidas: {', '.join(status_validos)}"
            })
            
        return novo_status

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ServiceRequest.objects.none()

        user = self.request.user
        queryset = ServiceRequest.objects.select_related(
            'tipo', 'solicitante', 'executor'
        ).prefetch_related('anexos', 'unidades').order_by('-created_at')

        # 1. Admin vê TUDO
        if user.is_superuser or getattr(user, 'is_admin', False):
            return queryset
            
        # 2. Parceiro Externo vê apenas as solicitações dos tipos que ele atende
        if getattr(user, 'is_externo', False):
            return queryset.filter(tipo__in=user.tipos_servico.all())
            
        # 3. Cliente comum vê apenas as suas próprias solicitações
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
        user = request.user

        # 1. Permissão DRY: Usa o Mixin centralizado
        self.check_team_permission(request, service)
        
        # Leitura do status atual e validação do novo status
        novo_status = self.validar_novo_status(request.data.get('status')) 

        # 2. Bloqueio de redundância (Evita histórico e notificação duplicados)
        if novo_status == service.status:
            return Response({"detail": f"A solicitação já está no status {service.get_status_display()}."}, status=status.HTTP_200_OK)

        # --- CORREÇÃO P1-7: Bloqueio de transições inválidas por tipo de serviço ---
        tipo_codigo = service.tipo.codigo if service.tipo else ""
        
        # A. Consulta de carga e Lista de compensação não têm fluxo de pendência
        if tipo_codigo in ['consulta_carga', 'lista_compensacao']:
            if novo_status in [ServiceRequest.StatusChoices.PENDENCIAS]:
                return Response(
                    {"status": f"O serviço '{service.tipo.nome}' não possui fluxo de pendências."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        # B. Lista de compensação termina em SERVICO_SOLICITADO, não em CONCLUIDO
        if tipo_codigo == 'lista_compensacao' and novo_status == ServiceRequest.StatusChoices.CONCLUIDO:
            return Response(
                {"status": "A Lista de Compensação termina no status SERVICO_SOLICITADO e não pode ser marcada como CONCLUIDO."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

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

        campos_resultado = [
            'protocolo', 'uc_resultado', 'prazo_concessionaria', 
            'nota', 'carga', 'tensao_nominal', 'potencia_transformador'
        ]
        
        for campo in campos_resultado:
            if campo in request.data:
                valor = request.data.get(campo)
                if valor == "":
                    valor = None
                setattr(service, campo, valor)

        if novo_status == ServiceRequest.StatusChoices.REALIZANDO and not service.executor:
            service.executor = user


        # 2. NOVA VALIDAÇÃO SOBRE O OBJETO (COPIE E COLE ESTE BLOCO)
        erros = {}
        if novo_status == ServiceRequest.StatusChoices.CONCLUIDO:
            if tipo_codigo == 'consulta_carga':
                if service.carga is None: erros['carga'] = "A carga é obrigatória para concluir a consulta."
                if not service.tensao_nominal: erros['tensao_nominal'] = "A tensão nominal é obrigatória."
                if service.potencia_transformador is None: erros['potencia_transformador'] = "A potência do transformador é obrigatória."
            
            elif tipo_codigo in ['ligacao_nova', 'alteracao_carga_fase', 'alteracao_carga']:
                if not service.protocolo: erros['protocolo'] = "O protocolo é obrigatório."
                if not service.uc_resultado: erros['uc_resultado'] = "A UC Resultado é obrigatória para conclusão."
                if not service.prazo_concessionaria: erros['prazo_concessionaria'] = "O prazo da concessionária é obrigatório."
                
            elif tipo_codigo == 'troca_titularidade':
                unidades = service.unidades.all()
                if not unidades.exists() or any(not u.uc_antiga or not u.uc_nova for u in unidades):
                    erros['unidades'] = "Todas as unidades envolvidas devem ter o par 'uc_antiga' e 'uc_nova' preenchidos para concluir a troca."
                    
        elif novo_status == ServiceRequest.StatusChoices.SERVICO_SOLICITADO:
            if tipo_codigo == 'lista_compensacao' and not service.protocolo:
                erros['protocolo'] = "O protocolo é obrigatório para enviar a lista de compensação."

        if erros:
            return Response(erros, status=status.HTTP_400_BAD_REQUEST)
        

        # Atribuição dos campos de resultado enviados no request, EXECUTOR não entra aqui, pois é preenchido automaticamente
        campos_resultado = [
            'protocolo', 'uc_resultado', 'prazo_concessionaria', 
            'nota', 'carga', 'tensao_nominal', 'potencia_transformador'
        ]
        
        for campo in campos_resultado:
            if campo in request.data:
                valor = request.data.get(campo)
                # Converte strings vazias para None para campos Date/Decimal
                if valor == "":
                    valor = None
                setattr(service, campo, valor)

        # 5. Preenchimento automático (e não manual) do Executor
        if novo_status == ServiceRequest.StatusChoices.REALIZANDO and not service.executor:
            service.executor = user

        # 6. Exigência de campos obrigatórios por Tipo e Status
        tipo_codigo = service.tipo.codigo if service.tipo else ""
        erros = {}

                    
        if novo_status == ServiceRequest.StatusChoices.SERVICO_SOLICITADO:
            if tipo_codigo == 'lista_compensacao' and not service.protocolo:
                erros['protocolo'] = "O protocolo é obrigatório para enviar a lista de compensação."

        if erros:
            return Response(erros, status=status.HTTP_400_BAD_REQUEST)
        
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

    def check_read_permission(self, parent_obj):
        """
        Obrigatório pelo AbstractDocumentListViewSet.
        Delega a validação de acesso ao ServiceAccessMixin, que já sabe
        exatamente se o usuário (Admin, Externo ou Cliente) tem permissão
        para aceder à solicitação (parent_obj).
        """
        self.check_access_permission(parent_obj)

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
            # --- CORREÇÃO P1-12: Bloqueio total de exclusão para clientes ---
            # Clientes não apagam anexos. Eles apenas substituem (PATCH) anexos reprovados.
            raise PermissionDenied(
                "Clientes não têm permissão para excluir anexos. "
                "Se um documento foi reprovado, utilize a opção de reenvio para substituí-lo."
            )
                
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
        self.check_team_permission(self.request, service)

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

class ServiceAttachmentDownloadView(ServiceAccessMixin, AbstractDocumentDownloadView):
    model = ServiceAttachment
    parent_model = ServiceRequest
    parent_url_kwarg = 'parent_pk'
    document_url_kwarg = 'document_pk'
    
    # Adicione esta linha:
    parent_relation_field = 'service'

    def check_download_permission(self, request, service, document):
        if request.user == service.solicitante:
            return
            
        # Se não for o dono, verifica se é da equipa responsável
        self.check_team_permission(request, service)


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
            self.check_team_permission(self.request,service)
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

class ServiceAttachmentDownloadAllView(ServiceAccessMixin, AbstractDocumentDownloadAllView):
    model = ServiceAttachment
    parent_model = ServiceRequest
    parent_relation_field = 'service'
    parent_url_kwarg = 'parent_pk'

    def check_download_all_permission(self, request, service):
        if request.user == service.solicitante:
            return
            
        self.check_team_permission(request, service)