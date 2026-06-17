import logging
import os
from django.conf import settings
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from email.mime.image import MIMEImage

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import transaction
from solar.notifications.models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()

# ==============================================================================
# 🟢 CAMADA 1: CORE / BASE ABSOLUTA
# ==============================================================================
def _enviar_payload_websocket(group_name, title, message, url=""):
    channel_layer = get_channel_layer()
    payload = {
        'type': 'send_notification',
        'data': {
            'title': title, 
            'message': message,
            'url': url,
            'timestamp': timezone.now().isoformat()
        }
    }
    async_to_sync(channel_layer.group_send)(group_name, payload)

def _enviar_email_template(to_emails, subject, template_name, context):
    try:
        if isinstance(to_emails, str):
            to_emails = [to_emails]
            
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_emails
        )
        msg.attach_alternative(html_content, "text/html")

        # 🟢 REMOVIDO: O bloco antigo de anexo MIMEImage que o Brevo rejeitava.
        # Agora o HTML vai buscar a logo diretamente via URL da web.

        msg.send(fail_silently=False)
        logger.info(f"E-mail enviado com sucesso para {to_emails}")
        return True
    except Exception as e:
        logger.error(f"Falha crítica no disparo de e-mail: {str(e)}")
        return False


# ==============================================================================
# 🟡 CAMADA 2: ROTEAMENTO E TRANSAÇÃO
# ==============================================================================
def _rotear_e_salvar_notificacao(projeto, sender, publico_alvo, title, message, category, url="", cliente=None, email_data=None):
    if publico_alvo == 'cliente':
        usuario_alvo = cliente or (projeto.created_by if projeto else None)
        destinatarios = [usuario_alvo] if usuario_alvo else []
        emails_destino = [usuario_alvo.email] if (usuario_alvo and usuario_alvo.email) else []
        group_name = f'user_notifications_{usuario_alvo.pk}' if usuario_alvo else None
    elif publico_alvo == 'admins':
        destinatarios = list(User.objects.filter(is_admin=True))
        emails_destino = [admin.email for admin in destinatarios if admin.email]
        group_name = "Administradores"
    else:
        logger.error(f"Público alvo '{publico_alvo}' desconhecido.")
        return

    if not destinatarios:
        return

    try:
        with transaction.atomic():
            # PASSO A: Salvar no Banco
            notificacoes_para_criar = [
                Notification(project=projeto, sender=sender, recipient=user, 
                             title=title, message=message, category=category)
                for user in destinatarios if user
            ]
            Notification.objects.bulk_create(notificacoes_para_criar)

            # PASSO B: Disparar E-mail
            if email_data and emails_destino:
                sucesso_email = _enviar_email_template(
                    to_emails=emails_destino,
                    subject=email_data['subject'],
                    template_name=email_data['template'],
                    context=email_data['context']
                )
                if not sucesso_email:
                    raise Exception("Rollback ativado: Falha no envio de e-mail.")

        # PASSO C: WebSocket
        if group_name:
            _enviar_payload_websocket(group_name, title, message, url)
            logger.info(f"Notificação '{category}' enviada com sucesso para {publico_alvo}.")

    except Exception as e:
        logger.error(f"Notificação abortada. Motivo: {str(e)}")


# ==============================================================================
# 🟠 CAMADA 3: CENTRAL DE REGRAS 
# ==============================================================================
def _construir_mensagem_notificacao(projeto, evento, context, sender=None):
    title = ""
    message = ""
    category = ""
    publico_alvo = ""
    url = ""
    email_data = None
    
    cliente_direto = context.get('cliente')

    # --- EVENTOS DE PROJETO ---
    if evento == 'documento_rejeitado':
        publico_alvo = 'cliente'
        documento = context.get('documento')
        nome_doc = documento.get_document_type_display() if documento else "documento"
        motivo = documento.rejection_reason if (documento and documento.rejection_reason) else "Verifique as pendências no painel."
        
        category = "DOCUMENTO_RECUSADO"
        title = f"{nome_doc.title()} Recusado"
        message = f"Seu arquivo '{nome_doc}' do projeto {projeto.codigoCliente} não foi aceito. Motivo: {motivo}"
        email_data = {
            'subject': f"Pendência no seu Projeto Solar - {projeto.codigoCliente}",
            'template': 'email/client/documento_rejeitado.html',
            'context': {'projeto': projeto, 'nome_documento': nome_doc, 'motivo': motivo}
        }

    elif evento == 'documento_aprovado':
        publico_alvo = 'cliente'
        documento = context.get('documento')
        nome_doc = documento.get_document_type_display() if documento else "documento"
        
        category = "DOCUMENTO_APROVADO"
        title = f"{nome_doc.title()} Aprovado!"
        message = f"O seu arquivo '{nome_doc}' do projeto {projeto.codigoCliente} foi analisado e aprovado."
        email_data = {
            'subject': f"Documento Aprovado - Projeto {projeto.codigoCliente}",
            'template': 'email/client/documento_aprovado.html',
            'context': {'projeto': projeto, 'nome_documento': nome_doc}
        }
    
    # --- NOVO EVENTO: CRIAÇÃO DE PROJETO ---
    elif evento == 'novo_projeto_criado':
        publico_alvo = 'admins'
        category = "NOVO_PROJETO"
        title = "Novo Projeto Adicionado"
        message = f"O projeto {projeto.codigoCliente} ({projeto.nomeTitular}) foi registado no sistema."
        url = f"/admin/projetos/{projeto.pk}/"
        email_data = {
            'subject': f"[SISTEMA] Novo Projeto Registado - {projeto.codigoCliente}",
            'template': 'email/admin/novo_projeto.html',
            'context': {'projeto': projeto, 'url_painel': url}
        }
        
    elif evento == 'boleto_adicionado':
        publico_alvo = 'cliente'
        category = "BOLETO_ADICIONADO"
        title = "Novo Boleto Disponível"
        message = f"Um novo boleto foi anexado ao seu projeto {projeto.codigoCliente}."
        email_data = {
            'subject': f"Seu boleto está disponível - Projeto {projeto.codigoCliente}",
            'template': 'email/client/boleto_disponivel.html',
            'context': {'projeto': projeto}
        }

    elif evento == 'status_projeto_alterado':
        publico_alvo = 'cliente'
        category = "STATUS_ALTERADO"
        title = "Status do Projeto Atualizado"
        message = f"O status do seu projeto {projeto.codigoCliente} mudou de '{context.get('status_antigo')}' para '{context.get('status_novo')}'."
        email_data = {
            'subject': f"Atualização de Status - Projeto {projeto.codigoCliente}",
            'template': 'email/client/status_alterado.html',
            'context': {'projeto': projeto, 'status_antigo': context.get('status_antigo'), 'status_novo': context.get('status_novo')}
        }
        
    elif evento == 'protocolo_atualizado':
        publico_alvo = 'admins'
        category = "PROTOCOLO_ATUALIZADO"
        title = f"Protocolo Atualizado - {projeto.codigoCliente}"
        
        data_limite_br = context.get('data_limite')
        if data_limite_br:
            if isinstance(data_limite_br, str) and '-' in data_limite_br:
                try:
                    ano, mes, dia = data_limite_br.split('-')
                    data_limite_br = f"{dia}/{mes}/{ano}"
                except ValueError:
                    pass
            elif hasattr(data_limite_br, 'strftime'):
                data_limite_br = data_limite_br.strftime('%d/%m/%Y')
        else:
            data_limite_br = "Não informada"

        numero_proto = context.get('numero_protocolo')
        message = f"O projeto {projeto.codigoCliente} recebeu: Protocolo {numero_proto}. Vencimento: {data_limite_br}."
        url = f"/admin/projetos/{projeto.pk}/"
        email_data = {
            'subject': f"[ALERTA TÉCNICO] Protocolo Inserido - {projeto.codigoCliente}",
            'template': 'email/admin/protocolo_atualizado.html',
            'context': {'projeto': projeto, 'numero_protocolo': numero_proto, 'data_limite': data_limite_br, 'url_painel': url}
        }

    elif evento == 'comprovante_adicionado':
        publico_alvo = 'admins'
        category = "COMPROVANTE_ENVIADO"
        title = "Novo Comprovante Recebido"
        message = f"O cliente {projeto.nomeTitular} enviou um comprovante de pagamento para o projeto {projeto.codigoCliente}."
        url = f"/admin/projetos/{projeto.pk}/"
        email_data = {
            'subject': f"[FINANCEIRO] Comprovante Recebido - {projeto.nomeTitular}",
            'template': 'email/admin/comprovante_recebido.html',
            'context': {'projeto': projeto, 'url_painel': url}
        }

    elif evento == 'vistoria_solicitada':
        publico_alvo = 'admins'
        category = "VISTORIA_SOLICITADA"
        title = "Solicitação de Vistoria"
        message = f"O usuário {sender.get_full_name() if sender else 'Cliente'} solicitou uma vistoria para o projeto {projeto.codigoCliente}."
        url = f"/admin/projetos/{projeto.pk}/"
        email_data = {
            'subject': f"[OPERACIONAL] Nova Vistoria Solicitada - {projeto.codigoCliente}",
            'template': 'email/admin/vistoria_solicitada.html',
            'context': {'projeto': projeto, 'url_painel': url}
        }

    # --- NOVOS EVENTOS: DOCUMENTOS DIRETOS DO USUÁRIO ---
    elif evento == 'user_boleto_adicionado':
        publico_alvo = 'cliente'
        category = "BOLETO_ADICIONADO"
        title = "Novo Boleto de Cadastro"
        message = "Um novo boleto de pagamento geral foi anexado ao seu perfil administrativo. Acesse para baixar."
        url = "/meus-documentos/"
        email_data = {
            'subject': "Novo Boleto Disponível na sua Conta",
            'template': 'email/client/user_boleto_disponivel.html',
            'context': {'cliente': cliente_direto}
        }

    elif evento == 'user_comprovante_adicionado':
        publico_alvo = 'admins'
        category = "COMPROVANTE_ENVIADO"
        nome_cliente = cliente_direto.get_full_name() if cliente_direto else "Um cliente"
        title = "Novo Comprovante de Usuário"
        message = f"O usuário {nome_cliente} enviou um comprovante de pagamento direto no perfil."
        url = f"/admin/usuarios/{cliente_direto.pk}/" if cliente_direto else ""
        email_data = {
            'subject': f"[FINANCEIRO] Comprovante Avulso Recebido - {nome_cliente}",
            'template': 'email/admin/user_comprovante_recebido.html',
            'context': {'cliente': cliente_direto, 'url_painel': url}
        }

    else:
        logger.error(f"Evento desconhecido: {evento}")
        return

    _rotear_e_salvar_notificacao(
        projeto=projeto,
        sender=sender,
        publico_alvo=publico_alvo,
        title=title,
        message=message,
        category=category,
        url=url,
        cliente=cliente_direto,
        email_data=email_data
    )

# ==============================================================================
# 🔵 CAMADA 4: FUNÇÕES ESPECIALIZADAS
# ==============================================================================

# --- Destinadas ao Cliente ---
def notify_document_rejected(projeto, documento):
    _construir_mensagem_notificacao(projeto, 'documento_rejeitado', context={'documento': documento})

def notify_document_approved(projeto, documento):
    _construir_mensagem_notificacao(projeto, 'documento_aprovado', context={'documento': documento})

def notify_boleto_added(projeto, documento):
    _construir_mensagem_notificacao(projeto, 'boleto_adicionado', context={'documento': documento})

def notify_project_status_changed(projeto, status_antigo, status_novo):
    _construir_mensagem_notificacao(projeto, 'status_projeto_alterado', context={
        'status_antigo': status_antigo,
        'status_novo': status_novo
    })

# --- Sem projeto atrelado, apenas user ---
def notify_user_boleto_added(cliente, documento):
    _construir_mensagem_notificacao(projeto=None, evento='user_boleto_adicionado', context={
        'cliente': cliente,
        'documento': documento
    })

def notify_user_comprovante_added(cliente, documento, cliente_remetente):
    # Corrigido o nome do evento aqui para bater com o if da Camada 3
    _construir_mensagem_notificacao(projeto=None, evento='user_comprovante_adicionado', context={
        'cliente': cliente,
        'documento': documento
    }, sender=cliente_remetente)
    

# --- Destinadas aos Administradores ---
def notify_protocol_updated(projeto, numero_protocolo, data_limite):
    _construir_mensagem_notificacao(projeto, 'protocolo_atualizado', context={
        'numero_protocolo': numero_protocolo,
        'data_limite': data_limite
    })

def notify_new_project_created(projeto):
    _construir_mensagem_notificacao(projeto, 'novo_projeto_criado', context={})

def notify_comprovante_added(projeto, documento, cliente_remetente):
    _construir_mensagem_notificacao(projeto, 'comprovante_adicionado', context={'documento': documento}, sender=cliente_remetente)

def notify_inspection_requested(projeto, usuario_solicitante):
    _construir_mensagem_notificacao(projeto, 'vistoria_solicitada', context={}, sender=usuario_solicitante)