from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from djoser import utils
from djoser.conf import settings
from django.conf import settings as django_settings


class ActivationEmail:
    template_name = "email/activation.html"
    
    def __init__(self, request, context):
        self.request = request
        self.context = context
        self.user = context.get('user')
        
    def get_context_data(self):
        # Contexto para o template do email
        context = self.context.copy()
        user = context.get('user')
        
        context.update({
            'user': user,
            'domain': getattr(django_settings, 'DOMAIN', 'localhost:8000'),
            'site_name': getattr(django_settings, 'SITE_NAME', 'SolarEnergy'),
            'uid': utils.encode_uid(user.pk),
            'token': default_token_generator.make_token(user),
            'protocol': 'https' if self.request.is_secure() else 'http',
            'frontend_url': getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000'),
        })
        return context
    
    def get_subject(self):
        return f"Ative sua conta - {getattr(django_settings, 'SITE_NAME', 'SolarEnergy')}"
    
    def get_recipients(self):
        return [self.user.email]
    
    def send(self, to=None, *args, **kwargs):
        context = self.get_context_data()
        subject = self.get_subject()
        to = to or self.get_recipients()
        
        # Renderizar template HTML
        html_content = render_to_string(self.template_name, context)
        
        # Criar versão texto simples
        text_content = f"""

Bem-vindo ao {context['site_name']}!

Para ativar sua conta, clique no link abaixo:
{context['frontend_url']}/activate/{context['uid']}/{context['token']}

Se você não se cadastrou em nosso site, ignore este email.

Atenciosamente,
Equipe {context['site_name']}
        """.strip()
        
        # Criar email
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@solarenergy.com'),
            to=to,
        )
        
        # Adicionar versão HTML
        email.attach_alternative(html_content, "text/html")
        
        try:
            email.send()
            print(f"Email de ativação enviado para: {to}")
            return True
        except Exception as e:
            print(f"Erro ao enviar email de ativação: {e}")
            return False
