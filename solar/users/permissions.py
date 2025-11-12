from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
import logging

logger = logging.getLogger(__name__)

class AuthenticationThrottle(AnonRateThrottle):
    """
    Rate limit para endpoints de autenticação (login, registro)
    Mais restritivo para evitar brute force
    """
    scope = 'authentication'
    rate = '5/minute'  # 5 tentativas por minuto

class IsAdminUser(BasePermission):
    """
    Permite acesso apenas para admins
    """
    def has_permission(self, request, view):
        # Primeiro, verifica se o usuário está autenticado.
        # AnonymousUser.is_authenticated é False.
        if not request.user.is_authenticated:
            return False

        # Se autenticado, verifica se é admin ou superuser.
        return request.user.is_admin or request.user.is_superuser
    
class IsOwnerOrAdmin(BasePermission):
    """
    Permite que o usuário acesse seus próprios dados ou admins acessem qualquer um
    """
    def has_object_permission(self, request, view, obj):
        if request.user.is_admin or request.user.is_superuser:
            return True
        return obj == request.user

class CanDeleteUser(BasePermission):
    """
    Permite deleção apenas para admins (sem senha) ou o próprio usuário (com senha)
    """
    def has_object_permission(self, request, view, obj):
        # Admin pode deletar qualquer um
        if request.user.is_admin or request.user.is_superuser:
            return True
        # Usuário comum só pode deletar a si mesmo
        return obj == request.user

class LoginThrottle(AnonRateThrottle):
    """Rate limit para login - 5 tentativas por minuto"""
    scope = 'login'
    rate = '5/minute'

class RegistrationThrottle(AnonRateThrottle):
    """Rate limit para registro - 3 por hora"""
    scope = 'registration'
    rate = '3/hour'

class ActivationThrottle(AnonRateThrottle):
    """Rate limit para ativação - 10 por hora"""
    scope = 'activation'
    rate = '10/hour'

class PasswordResetThrottle(AnonRateThrottle):
    """Rate limit para reset de senha - 3 por hora"""
    scope = 'password_reset'
    rate = '3/hour'

class UserDeleteThrottle(UserRateThrottle):
    """Rate limit para deleção de usuário - 5 por dia"""
    scope = 'user_delete'
    rate = '5/day'

class GeneralUserThrottle(UserRateThrottle):
    """Rate limit geral para usuários autenticados"""
    scope = 'general_user'
    rate = '1000/hour'

class GeneralAnonThrottle(AnonRateThrottle):
    """Rate limit geral para usuários anônimos"""
    scope = 'general_anon'
    rate = '100/hour'
