from djoser.email import ActivationEmail as BaseActivationEmail
from djoser.email import ConfirmationEmail as BaseConfirmationEmail
from djoser.email import PasswordResetEmail as BasePasswordResetEmail
from djoser.email import PasswordChangedConfirmationEmail as BasePasswordChangedConfirmationEmail
from djoser.email import UsernameChangedConfirmationEmail as BaseUsernameChangedConfirmationEmail
from djoser.email import UsernameResetEmail as BaseUsernameResetEmail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class ActivationEmail(BaseActivationEmail):
    template_name = 'email/activation.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        # Obter configurações do Django settings
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        # Construir URL de ativação personalizada
        user = context.get('user')
        uuid = context.get('uuid')
        token = context.get('token')
        
        # URL personalizada que aponta para nossa view customizada
        activation_url = f"{settings.BASE_URL}/activate/{uuid}/{token}/"
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
            'activation_url': activation_url,  # URL personalizada
            'user': user,
            'uuid': uuid,
            'token': token,
        })
        
        logger.info(f"Email de ativação preparado para usuário: {user.email if user else 'N/A'}")
        return context


class ConfirmationEmail(BaseConfirmationEmail):
    template_name = 'email/confirmation.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
        })
        
        logger.info("Email de confirmação preparado")
        return context


class PasswordResetEmail(BasePasswordResetEmail):
    template_name = 'email/password_reset.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')

        # --- ADICIONE ESTAS LINHAS ---
        _protocol = "http" 
                          
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080') # Pega do settings.DOMAIN que configuramos no docker-compose
        _static_url = settings.STATIC_URL
        
        # Construir URL de reset de senha para o frontend
        uid = context.get('uid')
        token = context.get('token')
        password_reset_url = f"{frontend_url}/password/reset/confirm/{uid}/{token}/"
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
            'password_reset_url': password_reset_url,
            'uid': uid,
            'token': token,
            'protocol': _protocol,
            'domain': _domain,
            'STATIC_URL': _static_url,
        })
        
        logger.info("Email de reset de senha preparado")
        generated_logo_url = f"{_protocol}://{_domain}{_static_url}images/logo-com-nome.png"
        logger.info(f"DEBUG: URL da logo gerada para o e-mail: {generated_logo_url}")
        return context


class PasswordChangedConfirmationEmail(BasePasswordChangedConfirmationEmail):
    template_name = 'email/password_changed_confirmation.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
            'login_url': f"{frontend_url}/login/",
        })
        
        logger.info("Email de confirmação de mudança de senha preparado")
        return context


class UsernameChangedConfirmationEmail(BaseUsernameChangedConfirmationEmail):
    template_name = 'email/username_changed_confirmation.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
            'login_url': f"{frontend_url}/login/",
        })
        
        logger.info("Email de confirmação de mudança de username preparado")
        return context


class UsernameResetEmail(BaseUsernameResetEmail):
    template_name = 'email/username_reset.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        # Construir URL de reset de username para o frontend
        uid = context.get('uid')
        token = context.get('token')
        username_reset_url = f"{frontend_url}/username/reset/confirm/{uid}/{token}/"
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
            'username_reset_url': username_reset_url,
            'uid': uid,
            'token': token,
        })
        
        logger.info("Email de reset de username preparado")
        return context
