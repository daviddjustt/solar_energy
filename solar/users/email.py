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
        site_name = getattr(settings, 'SITE_NAME', 'SolarEnergy')
        
        # Construir URL de ativação personalizada
        user = context.get('user')
        uid = context.get('uid')
        token = context.get('token')
        
        # URL personalizada que aponta para nossa view customizada
        activation_url = f"{settings.BASE_URL}/activate/{uid}/{token}/"
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
            'activation_url': activation_url,  # URL personalizada
            'user': user,
            'uid': uid,
            'token': token,
        })
        
        logger.info(f"Email de ativação preparado para usuário: {user.email if user else 'N/A'}")
        return context


class ConfirmationEmail(BaseConfirmationEmail):
    template_name = 'email/confirmation.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        site_name = getattr(settings, 'SITE_NAME', 'SolarEnergy')
        
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
        site_name = getattr(settings, 'SITE_NAME', 'SolarEnergy')
        
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
        })
        
        logger.info("Email de reset de senha preparado")
        return context


class PasswordChangedConfirmationEmail(BasePasswordChangedConfirmationEmail):
    template_name = 'email/password_changed_confirmation.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        site_name = getattr(settings, 'SITE_NAME', 'SolarEnergy')
        
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
        site_name = getattr(settings, 'SITE_NAME', 'SolarEnergy')
        
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
        site_name = getattr(settings, 'SITE_NAME', 'SolarEnergy')
        
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
