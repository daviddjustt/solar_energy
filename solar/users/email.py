from djoser.email import ActivationEmail as BaseActivationEmail
from djoser.email import PasswordResetEmail as BasePasswordResetEmail
from djoser.email import PasswordChangedConfirmationEmail as BasePasswordChangedConfirmationEmail
from djoser.email import UsernameChangedConfirmationEmail as BaseUsernameChangedConfirmationEmail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class ActivationEmail(BaseActivationEmail):
    template_name = 'email/activation.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        # Variáveis necessárias para a logo e textos
        _protocol = "https" if getattr(settings, 'IS_PRODUCTION', False) else "http"
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080')
        _static_url = settings.STATIC_URL
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        context.update({
            'site_name': site_name,
            'protocol': _protocol,
            'domain': _domain,
            'STATIC_URL': _static_url,
            # A variável 'url' já é injetada nativamente pelo Djoser aqui
        })
        
        user = context.get('user')
        logger.info(f"Email de ativação preparado para usuário: {user.email if user else 'N/A'}")
        return context

class PasswordResetEmail(BasePasswordResetEmail):
    template_name = 'email/password_reset.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL')
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')

        _protocol = "https" if getattr(settings, 'IS_PRODUCTION', False) else "http"
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080')
        _static_url = settings.STATIC_URL
        
        # Construir URL de reset de senha para o frontend
        uid = context.get('uid')
        token = context.get('token')
        password_reset_url = f"{frontend_url}/resetPassword/{uid}/{token}/"
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
            'password_reset_url': password_reset_url,
            'protocol': _protocol,
            'domain': _domain,
            'STATIC_URL': _static_url,
        })
        
        logger.info("Email de reset de senha preparado")
        return context

# As classes de Confirmação podem se manter como estavam,
# mas se elas tiverem logo no HTML delas, você precisará injetar protocol, domain e STATIC_URL lá também.
class PasswordChangedConfirmationEmail(BasePasswordChangedConfirmationEmail):
    template_name = 'email/password_changed_confirmation.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL')
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
            'login_url': f"{frontend_url}/login/",
        })
        
        return context

class UsernameChangedConfirmationEmail(BaseUsernameChangedConfirmationEmail):
    template_name = 'email/username_changed_confirmation.html'
    
    def get_context_data(self):
        context = super().get_context_data()
        
        frontend_url = getattr(settings, 'FRONTEND_URL')
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        context.update({
            'frontend_url': frontend_url,
            'site_name': site_name,
            'login_url': f"{frontend_url}/login/",
        })
        
        return context