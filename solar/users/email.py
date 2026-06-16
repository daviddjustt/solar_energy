from djoser.email import ActivationEmail as BaseActivationEmail
from djoser.email import PasswordResetEmail as BasePasswordResetEmail
from djoser.email import PasswordChangedConfirmationEmail as BasePasswordChangedConfirmationEmail
from djoser.email import UsernameChangedConfirmationEmail as BaseUsernameChangedConfirmationEmail
from templated_mail.mail import BaseEmailMessage

from django.conf import settings
from django.utils import timezone

import logging

logger = logging.getLogger(__name__)

class DocumentApprovedEmail(BaseEmailMessage):
    """Email disparado para o cliente quando um comprovante/documento é aprovado."""
    template_name = 'email/document_approved.html'

    def get_context_data(self):
        context = super().get_context_data()
        documento = context.get('documento')
        projeto = context.get('projeto')
        
        _protocol = "https" if getattr(settings, 'IS_PRODUCTION', False) else "http"
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080')
        
        context.update({
            'site_name': getattr(settings, 'SITE_NAME', 'SN Tech Solar'),
            'protocol': _protocol,
            'domain': _domain,
            'STATIC_URL': settings.STATIC_URL,
            'nome_titular': getattr(projeto, 'nomeTitular', 'Cliente'),
            'codigo_cliente': getattr(projeto, 'codigoCliente', 'N/A'),
            'tipo_documento': documento.get_document_type_display() if documento else 'Documento',
            'frontend_url': getattr(settings, 'FRONTEND_URL', f"{_protocol}://{_domain}")
        })
        return context

class BoletoAdicionadoEmail(BaseEmailMessage):
    """Email disparado para o cliente quando a empresa anexa um boleto."""
    template_name = 'email/boleto_adicionado.html'

    def get_context_data(self):
        context = super().get_context_data()
        projeto = context.get('projeto')
        
        _protocol = "https" if getattr(settings, 'IS_PRODUCTION', False) else "http"
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080')
        
        context.update({
            'site_name': getattr(settings, 'SITE_NAME', 'SN Tech Solar'),
            'protocol': _protocol,
            'domain': _domain,
            'STATIC_URL': settings.STATIC_URL,
            'nome_titular': getattr(projeto, 'nomeTitular', 'Cliente'),
            'codigo_cliente': getattr(projeto, 'codigoCliente', 'N/A'),
            'frontend_url': getattr(settings, 'FRONTEND_URL', f"{_protocol}://{_domain}")
        })
        return context

class ComprovanteAdicionadoEmail(BaseEmailMessage):
    """Email disparado para os administradores quando o cliente anexa um comprovante."""
    template_name = 'email/comprovante_adicionado.html'

    def get_context_data(self):
        context = super().get_context_data()
        projeto = context.get('projeto')
        cliente_remetente = context.get('cliente')
        
        _protocol = "https" if getattr(settings, 'IS_PRODUCTION', False) else "http"
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080')
        
        context.update({
            'site_name': getattr(settings, 'SITE_NAME', 'SN Tech Solar'),
            'protocol': _protocol,
            'domain': _domain,
            'STATIC_URL': settings.STATIC_URL,
            'nome_titular': getattr(projeto, 'nomeTitular', 'Cliente'),
            'codigo_cliente': getattr(projeto, 'codigoCliente', 'N/A'),
            'email_remetente': getattr(cliente_remetente, 'email', 'N/A'),
            'frontend_url': getattr(settings, 'FRONTEND_URL', f"{_protocol}://{_domain}")
        })
        return context
    
class StatusProjetoChangedEmail(BaseEmailMessage):
    """
    Email disparado para o cliente quando o status do projeto dele muda.
    """
    template_name = 'email/status_projeto_changed.html'

    def get_context_data(self):
        context = super().get_context_data()
        
        projeto = context.get('projeto')
        status_antigo = context.get('status_antigo')
        status_novo = context.get('status_novo')
        
        _protocol = "https" if getattr(settings, 'IS_PRODUCTION', False) else "http"
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080')
        _static_url = settings.STATIC_URL
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        context.update({
            'site_name': site_name,
            'protocol': _protocol,
            'domain': _domain,
            'STATIC_URL': _static_url,
            'nome_titular': getattr(projeto, 'nomeTitular', 'Cliente'),
            'codigo_cliente': getattr(projeto, 'codigoCliente', 'N/A'),
            'status_novo_display': status_novo,
            'status_antigo_display': status_antigo,
            'data_mudanca': timezone.now().strftime('%d/%m/%Y às %H:%M'),
            'frontend_url': getattr(settings, 'FRONTEND_URL', f"{_protocol}://{_domain}")
        })
        
        logger.info(f"Email de mudança de status ({status_novo}) preparado para o projeto ID: {projeto.id if projeto else 'N/A'}")
        return context

class AdminProtocoloNotificationEmail(BaseEmailMessage):
    template_name = 'email/protocolo_changed.html'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Forçamos o assunto aqui para garantir que a Brevo nunca receba um e-mail sem assunto
        self.subject = "🚨 Nova notificação de protocolo"
        
    def get_context_data(self):
        context = super().get_context_data()
        projeto = context.get('projeto')
        dados_protocolo = context.get('dados_protocolo') # Os 2 campos que o cliente informou
        
        _protocol = "https" if getattr(settings, 'IS_PRODUCTION', False) else "http"
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080')
        
        context.update({
            'site_name': getattr(settings, 'SITE_NAME', 'SN Tech Solar'),
            'nome_titular': projeto.nomeTitular,
            'codigo_cliente': projeto.codigoCliente,
            'dados_protocolo': dados_protocolo,
        })
        return context
    
class VistoriaRequestEmail(BaseEmailMessage):
    """
    Email disparado para a administração quando um cliente solicita uma vistoria.
    """
    template_name = 'email/vistoria_request.html'

    def get_context_data(self):
        context = super().get_context_data()
        
        # Recupera o projeto e usuário passados no dicionário de contexto da View
        projeto = context.get('projeto')
        user = context.get('user')
        
        _protocol = "https" if getattr(settings, 'IS_PRODUCTION', False) else "http"
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080')
        _static_url = settings.STATIC_URL
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        # Variáveis exclusivas que vão renderizar dentro do seu HTML (vistoria_request.html)
        context.update({
            'site_name': site_name,
            'protocol': _protocol,
            'domain': _domain,
            'STATIC_URL': _static_url,
            'nome_titular': getattr(projeto, 'nomeTitular', 'N/A'),
            'codigo_cliente': getattr(projeto, 'codigoCliente', 'N/A'),
            'projeto_id': projeto.id if projeto else 'N/A',
            'user_email': user.email if user else 'N/A',
            'data_hora_pedido': timezone.now().strftime('%d/%m/%Y às %H:%M:%S')
        })
        
        logger.info(f"Email de solicitação de vistoria estruturado para o projeto ID: {projeto.id if projeto else 'N/A'}")
        return context

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

class DocumentRejectedEmail(BaseEmailMessage):
    """
    Email disparado para o cliente quando um documento do projeto é rejeitado.
    """
    template_name = 'email/document_rejected.html'

    def get_context_data(self):
        context = super().get_context_data()
        
        documento = context.get('documento')
        projeto = context.get('projeto')
        motivo = context.get('motivo', 'Motivo não especificado.')
        
        _protocol = "https" if getattr(settings, 'IS_PRODUCTION', False) else "http"
        _domain = getattr(settings, 'DOMAIN', 'localhost:8080')
        _static_url = settings.STATIC_URL
        site_name = getattr(settings, 'SITE_NAME', 'SN Tech Solar')
        
        context.update({
            'site_name': site_name,
            'protocol': _protocol,
            'domain': _domain,
            'STATIC_URL': _static_url,
            'nome_titular': getattr(projeto, 'nomeTitular', 'Cliente'),
            'codigo_cliente': getattr(projeto, 'codigoCliente', 'N/A'),
            'tipo_documento': documento.get_document_type_display() if documento else 'Documento',
            'nome_arquivo': documento.document_name or 'Sem nome',
            'motivo_rejeicao': motivo,
            'frontend_url': getattr(settings, 'FRONTEND_URL', f"{_protocol}://{_domain}")
        })
        
        logger.info(f"Email de documento rejeitado preparado para o projeto ID: {projeto.id if projeto else 'N/A'}")
        return context
    
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