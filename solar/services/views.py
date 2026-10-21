from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.db import transaction

from solar.services.models import ServiceType, ServiceRequest
from .serializers import ServiceTypeSerializer, ServiceRequestSerializer, ExternalUserSerializer
from solar.services.notifications import notificar_nova_solicitacao, notificar_mudanca_status
from solar.users.models import User

class ServiceTypeViewSet(viewsets.ModelViewSet):
    """
    GET/PATCH /service-types/[cite: 1]
    """
    queryset = ServiceType.objects.all()
    serializer_class = ServiceTypeSerializer
    
    def get_permissions(self):
        # Apenas os administradores podem alterar a tabela de valores e gerir os tipos[cite: 1].
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Substitua pela sua permissão customizada de IsAdmin se necessário
            return [permissions.IsAdminUser()] 
        return [permissions.IsAuthenticated()]


class ServiceRequestViewSet(viewsets.ModelViewSet):
    """
    GET/POST /api/v1/services/ e GET/PATCH /api/v1/services/{id}/[cite: 1]
    """
    serializer_class = ServiceRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # Admin vê todas as solicitações[cite: 1].
        if user.is_staff or getattr(user, 'is_admin', False):
            return ServiceRequest.objects.all()
            
        # Externo vê apenas as solicitações dos tipos de serviço para os quais tem autorização[cite: 1].
        elif getattr(user, 'is_externo', False):
            return ServiceRequest.objects.filter(tipo__in=user.tipos_servico.all())
            
        # Cliente vê apenas as suas próprias solicitações[cite: 1].
        return ServiceRequest.objects.filter(solicitante=user)

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        
        if getattr(user, 'is_externo', False) or getattr(user, 'is_admin', False) or user.is_staff:
            raise PermissionDenied("Apenas os clientes podem abrir novas solicitações.")
            
        service = serializer.save(solicitante=user)
        notificar_nova_solicitacao(service)

    @action(detail=True, methods=['post'])
    def status(self, request, pk=None):
        solicitacao = self.get_object()
        novo_status = request.data.get('status')
        
        if novo_status and novo_status != solicitacao.status:
            solicitacao.status = novo_status
            
            # Se a transição for para REPROVADO, guarde o motivo
            if novo_status == 'REPROVADO':
                solicitacao.motivo_reprova = request.data.get('motivo_reprova')
                
            # O utilizador que muda para "REALIZANDO_SERVICO" assume como executor
            if novo_status == 'REALIZANDO_SERVICO' and not solicitacao.executor:
                solicitacao.executor = request.user
                
            solicitacao.save()
            
            # Dispara a notificação de mudança de status para cliente e externos[cite: 1]
            notificar_mudanca_status(solicitacao)

        return Response({"detail": "Status atualizado."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get', 'post'])
    def attachments(self, request, pk=None):
        """
        GET/POST /services/{id}/attachments/[cite: 1].
        O boleto e o comprovativo de pagamento entram por esta via[cite: 1].
        """
        solicitacao = self.get_object()
        # Aqui ficará a lógica do GET (listar anexos) e POST (upload do ServiceAttachment)
        return Response({"detail": "Anexos endpoint."})

    @action(detail=True, methods=['get', 'post'])
    def pendencies(self, request, pk=None):
        """
        GET/POST /services/{id}/pendencies/[cite: 1].
        """
        solicitacao = self.get_object()
        return Response({"detail": "Pendências endpoint."})

class ExternalUserViewSet(viewsets.ModelViewSet):
    """
    GET/POST/PATCH /external-users/ (somente admin)[cite: 1]
    """
    serializer_class = ExternalUserSerializer
    # Permissão rigorosa: apenas administradores interagem com esta rota[cite: 1]
    permission_classes = [permissions.IsAdminUser] 

    def get_queryset(self):
        # Garante que só retorna e permite gerir utilizadores marcados como externos
        return User.objects.filter(is_externo=True)

    def perform_create(self, serializer):
        # Forçamos cnpj=None (e cpf=None, se existir) para contornar a restrição
        # de strings vazias (UNIQUE) no banco de dados.
        serializer.save(is_externo=True, cnpj=None, cpf=None)
