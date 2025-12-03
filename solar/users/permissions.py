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
