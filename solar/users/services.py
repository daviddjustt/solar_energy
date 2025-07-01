# solar/users/services.py

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """
    Serviço responsável pelo envio de emails relacionados aos usuários
    """
    
    @staticmethod
    def send_welcome_email(user, plain_password=None):
        """
        Envia email de boas-vindas para novos usuários
        
        Args:
            user: Instância do modelo User
            plain_password: Senha em texto plano (opcional)
            
        Returns:
            bool: True se enviado com sucesso, False caso contrário
        """
        try:
            logger.info(f"Iniciando envio de email de boas-vindas para {user.email}")
            
            # Dados do contexto para o template
            context = {
                'user': user,
                'user_name': user.get_full_name() or user.first_name or user.email.split('@')[0],
                'site_name': getattr(settings, 'SITE_NAME', 'SolarEnergy'),
                'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
                'plain_password': plain_password,
                'login_url': f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/login/",
            }
            
            # Renderizar template HTML
            html_message = render_to_string('emails/welcome_email.html', context)
            
            # Versão em texto plano (fallback)
            plain_message = strip_tags(html_message)
            
            # Enviar email
            result = send_mail(
                subject=f'Bem-vindo ao {context["site_name"]}!',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
            
            if result > 0:
                logger.info(f"Email de boas-vindas enviado com sucesso para {user.email}")
                return True
            else:
                logger.warning(f"Falha no envio do email para {user.email} - resultado: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enviar email de boas-vindas para {user.email}: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def send_password_notification(user, plain_password):
        """
        Envia email com credenciais de acesso (senha temporária)
        
        Args:
            user: Instância do modelo User
            plain_password: Senha em texto plano
            
        Returns:
            bool: True se enviado com sucesso, False caso contrário
        """
        try:
            logger.info(f"Enviando credenciais de acesso para {user.email}")
            
            context = {
                'user': user,
                'user_name': user.get_full_name() or user.first_name or user.email.split('@')[0],
                'site_name': getattr(settings, 'SITE_NAME', 'SolarEnergy'),
                'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
                'email': user.email,
                'password': plain_password,
                'login_url': f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/login/",
            }
            
            # Renderizar templates
            html_message = render_to_string('emails/credentials_email.html', context)
            plain_message = strip_tags(html_message)
            
            result = send_mail(
                subject=f'Suas credenciais de acesso - {context["site_name"]}',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
            
            if result > 0:
                logger.info(f"Credenciais enviadas com sucesso para {user.email}")
                return True
            else:
                logger.warning(f"Falha no envio das credenciais para {user.email}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enviar credenciais para {user.email}: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def send_account_created_notification(user, created_by_admin=False):
        """
        Envia notificação de conta criada (sem senha)
        
        Args:
            user: Instância do modelo User
            created_by_admin: Se a conta foi criada por um administrador
            
        Returns:
            bool: True se enviado com sucesso, False caso contrário
        """
        try:
            logger.info(f"Enviando notificação de conta criada para {user.email}")
            
            context = {
                'user': user,
                'user_name': user.get_full_name() or user.first_name or user.email.split('@')[0],
                'site_name': getattr(settings, 'SITE_NAME', 'SolarEnergy'),
                'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
                'created_by_admin': created_by_admin,
                'login_url': f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/login/",
                'reset_password_url': f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/password/reset/",
            }
            
            html_message = render_to_string('emails/account_created.html', context)
            plain_message = strip_tags(html_message)
            
            result = send_mail(
                subject=f'Sua conta foi criada - {context["site_name"]}',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
            
            if result > 0:
                logger.info(f"Notificação de conta criada enviada para {user.email}")
                return True
            else:
                logger.warning(f"Falha no envio da notificação para {user.email}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enviar notificação para {user.email}: {str(e)}", exc_info=True)
            return False
