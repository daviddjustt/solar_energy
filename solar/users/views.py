import logging
import traceback

# Django imports
from django.conf import settings
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView
from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate

# Third-party imports
from djoser.views import UserViewSet,TokenCreateView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.decorators import action

# Local application imports
from .models import User, UserChangeLog
from .serializers import UserUpdateSerializer, SpecialCPFTokenCreateSerializer


# Configure the logger
logger = logging.getLogger(__name__)

User = get_user_model()

class CustomUserViewSet(UserViewSet):
    """
    ViewSet personalizado que sobrescreve o UserViewSet do Djoser
    para limitar os campos que podem ser alterados e registrar histórico de alterações.
    """
    def get_serializer_class(self):
        """
        Retorna o serializador adequado com base na ação.
        Para atualização (update) do próprio usuário ('me'), retorna nosso UserUpdateSerializer.
        Para outras ações ou usuários (ex: admin atualizando outro usuário), usa o serializador padrão.
        """
        if self.action == 'me':
            if self.request.method in ['PUT', 'PATCH']:
                return UserUpdateSerializer
        # Para ações de admin (list, retrieve, create, update, partial_update, destroy)
        # ou para o endpoint 'me' com outros métodos, usa o serializador padrão do Djoser
        # que geralmente é UserSerializer ou similar dependendo da configuração do Djoser.
        # Se você precisa de um serializador diferente para admin, ajuste aqui.
        return super().get_serializer_class()

    def get_serializer_context(self):
        """
        Adiciona o request ao contexto do serializador para acesso ao usuário atual.
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def update(self, request, *args, **kwargs):
        """
        Sobrescreve o método update para garantir que apenas
        os campos permitidos sejam alterados e registrar o histórico manual (UserChangeLog).
        """
        instance = self.get_object() # Obtém a instância antes da atualização
        original_instance_values = {field: getattr(instance, field, None) for field in request.data.keys()} # Captura valores originais

        # Para usuários comuns, verificamos se estão tentando alterar campos proibidos
        if not request.user.is_admin and not request.user.is_superuser:
            allowed_fields = ['celular', 'photo'] # Campos permitidos para usuários comuns
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
                 fields_to_log_manually = ['celular', 'photo', 'name', 'cpf', 'patent', 'is_admin', 'is_operacoes', 'is_sac', 'sac_profile', 'is_active'] # Exemplo: loga mais campos se admin estiver atualizando
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

class SpecialUserCPFLoginView(TokenCreateView):
    serializer_class = SpecialCPFTokenCreateSerializer
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.user
        
        # Registra primeiro acesso especial se necessário
        if not user.primeiro_acesso_especial:
            user.primeiro_acesso_especial = timezone.now()
            user.save(update_fields=['primeiro_acesso_especial'])
            
            # Log da ação
            UserChangeLog.objects.create(
                user=user,
                changed_by=None,  # Sistema automático
                field_name='primeiro_acesso_especial',
                old_value=None,
                new_value=str(timezone.now())
            )
        
        # Gera token
        token = self._get_token(user)
        
        return Response({
            'access': str(token.access_token),
            'refresh': str(token),
        }, status=status.HTTP_200_OK)
    
    def _get_token(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return RefreshToken.for_user(user)
