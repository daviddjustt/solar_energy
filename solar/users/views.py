import logging
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
# Third-party imports
from djoser.views import UserViewSet
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

import base64
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views import View
from django.db import transaction
from rest_framework import generics, status, viewsets, permissions

from .models import User, UserChangeLog
from django.db.models import Q
from .serializers import UserUpdateSerializer, CustomUserDeleteSerializer, UserDetailSerializer, UserDetailSerializer2
from .permissions import IsAdminUser, IsOwnerOrAdmin, CanDeleteUser, PasswordResetThrottle, UserDeleteThrottle, GeneralUserThrottle, LoginThrottle, RegistrationThrottle, ActivationThrottle

logger = logging.getLogger(__name__)
User = get_user_model()

class ClientUserListView(APIView):
    """
    Endpoint para listar todos os usuários que são clientes.
    Não recebe parâmetros, apenas retorna a lista de clientes ativos.
    """
    permission_classes = [IsAuthenticated] # Apenas usuários autenticados podem acessar
    def get(self, request, *args, **kwargs):
        user_type = 'cliente'
        # Verifica se o usuário que faz a requisição é admin
        # (Opcional: remova esta verificação se qualquer usuário autenticado puder ver a lista de clientes)
        if not request.user.is_admin:
            return Response(
                {"detail": "Você não tem permissão para acessar este recurso."},
                status=status.HTTP_403_FORBIDDEN
            )

        if user_type == 'cliente':
            # Filtra por associação ao grupo 'Clientes'
            queryset = queryset.filter(groups__name='Clientes')

        # Verifica se existem clientes
        if not queryset.exists():
            return Response(
                {"detail": "Nenhum usuário cliente encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Serializa e retorna a lista de clientes
        serializer = UserDetailSerializer2(queryset.order_by('name'), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class FilteredUserListView(APIView):
    permission_classes = [IsAuthenticated] # Ou IsAdminUser, dependendo de quem pode ver isso

    def get(self, request, user_type, *args, **kwargs):
        # Apenas administradores podem acessar este endpoint
        if not request.user.is_staff and not request.user.is_superuser:
            return Response(
                {"detail": "Você não tem permissão para acessar este recurso."},
                status=status.HTTP_403_FORBIDDEN
            )

        queryset = User.objects.filter(is_active=True)

        if user_type == 'admin':
            # Filtra por is_staff OU is_superuser para definir 'admin'
            queryset = queryset.filter(groups__name='Administradores')
        elif user_type == 'cliente':
            # Filtra por associação ao grupo 'Clientes'
            queryset = queryset.filter(groups__name='Clientes')
        elif user_type == 'tecnico':
            # Filtra por associação ao grupo 'Tecnicos'
            queryset = queryset.filter(groups__name='Tecnicos')
        else:
            return Response(
                {"detail": "Tipo de usuário inválido. Use 'admin', 'cliente' ou 'tecnico'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not queryset.exists():
            return Response(
                {"detail": f"Nenhum usuário do tipo '{user_type}' encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Use o UserDetailSerializer aqui
        serializer = UserDetailSerializer(queryset.order_by('name'), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class CustomUserViewSet(UserViewSet):
    """
    ViewSet personalizado que sobrescreve o UserViewSet do Djoser
    para limitar os campos que podem ser alterados e registrar histórico de alterações.
    """

    # Throttles padrão para todas as ações
    throttle_classes = [GeneralUserThrottle]
    
    # Permissões padrão
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        """Retorna o serializador apropriado baseado na ação"""
        if self.action == 'me':
            if self.request.method in ['PUT', 'PATCH']:
                return UserUpdateSerializer
        elif self.action == 'destroy':
            return CustomUserDeleteSerializer
        
        return super().get_serializer_class()

    def get_permissions(self):
        """Define permissões por ação"""
        if self.action == 'create':
            permission_classes = []  # Qualquer um pode se registrar
        elif self.action == 'destroy':
            permission_classes = [CanDeleteUser]
        elif self.action in ['update', 'partial_update']:
            permission_classes = [IsOwnerOrAdmin]
        elif self.action in ['list', 'retrieve']:
            permission_classes = [IsAdminUser]
        else:
            permission_classes = [IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def get_throttles(self):
        """Define throttles por ação"""
        if self.action == 'create':
            self.throttle_classes = [RegistrationThrottle]
        elif self.action == 'activation':
            self.throttle_classes = [ActivationThrottle]
        elif self.action == 'destroy':
            self.throttle_classes = [UserDeleteThrottle]
        elif self.action == 'reset_password':
            self.throttle_classes = [PasswordResetThrottle]
        else:
            self.throttle_classes = [GeneralUserThrottle]
        
        return super().get_throttles()
    #
    def get_serializer_context(self):
        """
        Adiciona o request ao contexto do serializador para acesso ao usuário atual.
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        """Criar novo usuário com validação extra"""
        try:
            logger.info(f"Tentativa de registro: {request.data.get('email')}")
            response = super().create(request, *args, **kwargs)
            logger.info(f"Usuário registrado com sucesso: {request.data.get('email')}")
            return response
        except Exception as e:
            logger.error(f"Erro ao registrar usuário: {str(e)}")
            return Response(
                {'error': 'Erro ao registrar usuário'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
    def update(self, request, *args, **kwargs):
        """
        Sobrescreve o método update para garantir que apenas
        os campos permitidos sejam alterados e registrar o histórico manual (UserChangeLog).
        """
        instance = self.get_object() # Obtém a instância antes da atualização
        original_instance_values = {field: getattr(instance, field, None) for field in request.data.keys()} # Captura valores originais

        # Para usuários comuns, verificamos se estão tentando alterar campos proibidos
        if not request.user.is_admin and not request.user.is_superuser:
            allowed_fields = ['celular',] # Campos permitidos para usuários comuns
            for field in request.data.keys(): # Itera sobre as chaves do request.data
                if field not in allowed_fields:
                    return Response(
                        {field: f"Você não tem permissão para alterar este campo."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

        # Chama o método update original do Djoser para realizar a validação e salvamento
        response = super().update(request, *args, **kwargs)

        # Se a atualização foi bem-sucedida (status 2xx), registramos as alterações no log manual (UserChangeLog)
        if status.is_success(response.status_code):
            instance.refresh_from_db() # Recarrega a instância para obter os novos valores salvos
            # Registrando as alterações manualmente no UserChangeLog
            for field_name, new_value in request.data.items():
                 # Verifica se o campo está entre os que queremos logar manualmente via esta view
                 # E se o valor realmente mudou
                 # Note: A lógica de permissão acima já restringe campos para usuários comuns.
                 # Este log manual pode ser para campos específicos que você quer rastrear por esta interface.
                 # Ajuste a lista `fields_to_log_manually` conforme necessário.
                 fields_to_log_manually = ['celular', 'name', 'cnpj','cpf', 'is_admin', 'is_active'] # Exemplo: loga mais campos se admin estiver atualizando
                 if field_name in fields_to_log_manually:
                     old_value = original_instance_values.get(field_name)
                     # Compara o valor original com o novo valor salvo no banco
                     current_saved_value = getattr(instance, field_name, None)

                     # Trata booleanos e None/vazios para comparação consistente
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
                             logger.debug(f"Logged change for user {instance.email}: field='{field_name}', old='{old_val_str}', new='{new_val_str}' by user {request.user.email}")
                         except Exception as log_exc:
                             logger.error(f"Erro ao registrar UserChangeLog para o usuário {instance.email}, campo {field_name}: {log_exc}", exc_info=True)


        return response

    def destroy(self, request, *args, **kwargs):
        """Deletar usuário com validações de segurança"""
        instance = self.get_object()
        
        # Validar permissões
        if not (request.user.is_admin or request.user == instance):
            return Response(
                {'error': 'Você não tem permissão para deletar este usuário'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            logger.warning(f"Deletando usuário: {instance.email}")
            response = super().destroy(request, *args, **kwargs)
            logger.warning(f"Usuário deletado: {instance.email}")
            return response
        except Exception as e:
            logger.error(f"Erro ao deletar usuário {instance.email}: {str(e)}")
            return Response(
                {'error': 'Erro ao deletar usuário'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
    @action(detail=False, methods=['get'])
    def history(self, request):
        """
        Endpoint adicional para obter o histórico (django-simple-history) do usuário atual.
        Apenas para usuários autenticados.
        """
        user = self.request.user
        if not user.is_authenticated:
            return Response({"detail": "Authentication required"},
                            status=status.HTTP_401_UNAUTHORIZED)

        # Usa o histórico automático do django-simple-history
        # Você pode adicionar paginação aqui se o histórico for muito grande
        history_entries = user.history.all().order_by('-history_date') #.[:10] # Removido limite fixo de 10

        history_data = []
        for entry in history_entries:
            # Calcula a diferença entre esta versão e a anterior
            prev_record = entry.prev_record
            changes = {}
            if prev_record:
                 delta = entry.diff_against(prev_record)
                 if delta:
                      changes = {change.field: {
                          "old": str(change.old), # Converte para string para API
                          "new": str(change.new)  # Converte para string para API
                      } for change in delta.changes}
            # Adiciona a entrada ao resultado se houver mudanças ou se for a primeira entrada
            if changes or not prev_record:
                 history_data.append({
                     "date": entry.history_date,
                     "history_type": entry.history_type, # '+', '-', '~' (created, deleted, changed)
                     "history_user": str(entry.history_user) if entry.history_user else None, # Converte usuário para string
                     "changes": changes
                 })

        return Response(history_data)
        
    @action(detail=False, methods=['post'], throttle_classes=[PasswordResetThrottle])
    def reset_password(self, request):
        """Reset de senha"""
        try:
            logger.info(f"Tentativa de reset de senha: {request.data.get('email')}")
            response = super().reset_password(request)
            logger.info(f"Email de reset enviado")
            return response
        except Exception as e:
            logger.error(f"Erro no reset de senha: {str(e)}")
            return Response(
                {'error': 'Erro ao resetar senha'},
                status=status.HTTP_400_BAD_REQUEST
            )

class ActivateAccountView(View):
    
    def get(self, request, uuid, token):
        return self._activate_account(request, uuid, token)
    
    def post(self, request, uuid, token):
        return self._activate_account(request, uuid, token)
    
    def _activate_account(self, request, uuid_encoded, token):
        try:
            # CORREÇÃO: Decodificar o UUID base64
            uuid_str = self._decode_uuid(uuid_encoded)
            if not uuid_str:
                return self._error_response(
                    "UUID inválido",
                    status=400
                )
            
            # Buscar usuário pelo UUID decodificado
            user = self._get_user_by_uuid(uuid_str)
            if not user:
                return self._error_response(
                    "Usuário não encontrado",
                    status=404
                )
            
            # Verificar se já está ativo
            if user.is_active:
                return self._success_response(
                    "Conta já está ativa",
                    user_data=self._get_user_data(user),
                    already_active=True
                )
            
            # Validar token
            if not self._is_valid_token(user, token):
                return self._error_response(
                    "Token inválido ou expirado",
                    status=400
                )
            
            # Ativar usuário
            success = self._activate_user(user)
            if not success:
                return self._error_response(
                    "Erro interno ao ativar conta",
                    status=500
                )
            
            return self._success_response(
                "Conta ativada com sucesso!",
                user_data=self._get_user_data(user)
            )
            
        except Exception as e:
            logger.error(f"Erro inesperado na ativação: {e}")
            return self._error_response(
                "Erro interno do servidor",
                details=str(e),
                status=500
            )
    
    def _decode_uuid(self, uuid_encoded):
        """
        Decodifica UUID base64 para string normal.
        
        Args:
            uuid_encoded: UUID codificado em base64
            
        Returns:
            str: UUID decodificado ou None se inválido
        """
        try:
            # Decodificar base64
            decoded_bytes = base64.urlsafe_b64decode(uuid_encoded)
            uuid_str = decoded_bytes.decode('utf-8')
            
            logger.info(f"UUID decodificado: {uuid_encoded} -> {uuid_str}")
            return uuid_str
            
        except Exception as e:
            logger.error(f"Erro ao decodificar UUID {uuid_encoded}: {e}")
            return None
    
    def _get_user_by_uuid(self, uuid_str):
        """Busca usuário pelo UUID string."""
        try:
            return User.objects.get(uuid=uuid_str)
        except (User.DoesNotExist, ValidationError, ValueError) as e:
            logger.warning(f"Usuário não encontrado para UUID: {uuid_str} - Erro: {e}")
            return None
    
    def _is_valid_token(self, user, token):
        """Valida o token de ativação."""
        try:
            return default_token_generator.check_token(user, token)
        except Exception as e:
            logger.warning(f"Erro ao validar token: {e}")
            return False
    
    @transaction.atomic
    def _activate_user(self, user):
        """Ativa o usuário no banco de dados."""
        try:
            user.is_active = True
            user.updated_at = timezone.now()
            user.save(update_fields=['is_active', 'updated_at'])
            
            logger.info(f"Usuário ativado com sucesso: {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao ativar usuário {user.email}: {e}")
            return False
    
    def _get_user_data(self, user):
        """Retorna dados seguros do usuário."""
        return {
            'uuid': str(user.uuid),
            'email': user.email,
            'name': user.name,
            'is_active': user.is_active,
            'created_at': user.created_at.isoformat(),
            'activated_at': timezone.now().isoformat() if user.is_active else None
        }
    
    def _success_response(self, message, user_data=None, already_active=False):
        """Resposta de sucesso padronizada."""
        response_data = {
            'success': True,
            'message': message,
            'timestamp': timezone.now().isoformat(),
            'already_active': already_active
        }
        
        if user_data:
            response_data['user'] = user_data
        
        status_code = 200 if already_active else 201
        return JsonResponse(response_data, status=status_code)
    
    def _error_response(self, message, details=None, status=400):
        """Resposta de erro padronizada."""
        response_data = {
            'success': False,
            'error': message,
            'timestamp': timezone.now().isoformat()
        }
        
        if details:
            response_data['details'] = details
        
        return JsonResponse(response_data, status=status)

    @action(detail=False, methods=['post'], throttle_classes=[ActivationThrottle])
    def activation(self, request):
        """Ativar conta de usuário"""
        try:
            uid = request.data.get('uid')
            token = request.data.get('token')
            
            if not uid or not token:
                return Response(
                    {'error': 'UID e token são obrigatórios'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            logger.info(f"Tentativa de ativação com UID: {uid}")
            response = super().activation(request)
            logger.info(f"Conta ativada com sucesso")
            return response
        except Exception as e:
            logger.error(f"Erro na ativação: {str(e)}")
            return Response(
                {'error': 'Erro ao ativar conta'},
                status=status.HTTP_400_BAD_REQUEST
            )