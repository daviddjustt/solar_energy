import logging
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.db import transaction
from solar.notifications.models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()
# ==============================================================================
# 🟢 CAMADA 1: CORE / BASE ABSOLUTA (Sem alterações)
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


# ==============================================================================
# 🟡 CAMADA 2: ROTEAMENTO E TRANSAÇÃO (Adaptada para aceitar 'cliente' direto)
# ==============================================================================
def _rotear_e_salvar_notificacao(projeto, sender, publico_alvo, title, message, category, url="", cliente=None):
    """
    Agora aceita o argumento opcional 'cliente' para casos onde não há um projeto.
    """
    # 1. Definir os destinatários baseado no público alvo
    if publico_alvo == 'cliente':
        # Se veio o cliente direto (DocumentUser), usamos ele. Se não, pegamos do projeto.
        usuario_alvo = cliente or (projeto.created_by if projeto else None)
        destinatarios = [usuario_alvo] if usuario_alvo else []
        group_name = f'user_notifications_{usuario_alvo.pk}' if usuario_alvo else None
    elif publico_alvo == 'admins':
        destinatarios = list(User.objects.filter(is_admin=True))
        group_name = "Administradores"
    else:
        logger.error(f"Público alvo '{publico_alvo}' desconhecido.")
        return

    if not destinatarios:
        return

    # 2. Transação Atômica (O e-mail continua comentado, mas a segurança do rollback está ativa)
    try:
        with transaction.atomic():
            # PASSO A: Disparar E-mail (Obrigatoriedade futura)
            # ---------------------------------------------------------
            # sucesso_email = servico_de_email_ainda_nao_implementado(destinatarios, title, message)
            # if not sucesso_email:
            #     raise Exception("Falha no disparo de e-mail obrigatório.")
            # ---------------------------------------------------------

            # PASSO B: Salvar no Banco (project pode ser None se o seu modelo permitir null=True)
            notificacoes_para_criar = [
                Notification(project=projeto, sender=sender, recipient=user, 
                             title=title, message=message, category=category)
                for user in destinatarios if user
            ]
            Notification.objects.bulk_create(notificacoes_para_criar)

        # PASSO C: WebSocket
        if group_name:
            _enviar_payload_websocket(group_name, title, message, url)
            logger.info(f"Notificação '{category}' enviada com sucesso para {publico_alvo}.")

    except Exception as e:
        logger.error(f"Notificação abortada. Motivo: {str(e)}")


# ==============================================================================
# 🟠 CAMADA 3: CENTRAL DE REGRAS (Adicionado suporte a documentos de usuário)
# ==============================================================================
def _construir_mensagem_notificacao(projeto, evento, context, sender=None):
    title = ""
    message = ""
    category = ""
    publico_alvo = ""
    url = ""
    
    cliente_direto = context.get('cliente') # Resgata o cliente se enviado diretamente

    # --- EVENTOS DE PROJETO (Mantidos idênticos) ---
    if evento == 'documento_rejeitado':
        publico_alvo = 'cliente'
        documento = context.get('documento')
        nome_doc = documento.get_document_type_display() if documento else "documento"
        motivo = documento.rejection_reason if (documento and documento.rejection_reason) else "Verifique as pendências no painel."
        category = "DOCUMENTO_RECUSADO"
        title = f"❌ {nome_doc.title()} Recusado"
        message = f"Seu arquivo '{nome_doc}' do projeto {projeto.codigoCliente} não foi aceito. Motivo: {motivo}"

    elif evento == 'documento_aprovado':
        publico_alvo = 'cliente'
        documento = context.get('documento')
        nome_doc = documento.get_document_type_display() if documento else "documento"
        category = "DOCUMENTO_APROVADO"
        title = f"✅ {nome_doc.title()} Aprovado!"
        message = f"O seu arquivo '{nome_doc}' do projeto {projeto.codigoCliente} foi analisado e aprovado."

    elif evento == 'boleto_adicionado':
        publico_alvo = 'cliente'
        category = "BOLETO_ADICIONADO"
        title = "📄 Novo Boleto Disponível"
        message = f"Um novo boleto foi anexado ao seu projeto {projeto.codigoCliente}."

    elif evento == 'status_projeto_alterado':
        publico_alvo = 'cliente'
        category = "STATUS_ALTERADO"
        title = "🔄 Status do Projeto Atualizado"
        message = f"O status do seu projeto {projeto.codigoCliente} mudou de '{context.get('status_antigo')}' para '{context.get('status_novo')}'."

    elif evento == 'protocolo_atualizado':
        publico_alvo = 'admins'
        category = "PROTOCOLO_ATUALIZADO"
        title = f"📌 Protocolo Atualizado - {projeto.codigoCliente}"
        
        # Recupera e trata a data enviada (convertendo de YYYY-MM-DD para DD/MM/YYYY se for string)
        data_limite_br = context.get('data_limite')
        if data_limite_br:
            if isinstance(data_limite_br, str) and '-' in data_limite_br:
                try:
                    ano, mes, dia = data_limite_br.split('-')
                    data_limite_br = f"{dia}/{mes}/{ano}"
                except ValueError:
                    pass
            elif hasattr(data_limite_br, 'strftime'):  # Caso o model já entregue um objeto date/datetime
                data_limite_br = data_limite_br.strftime('%d/%m/%Y')
        else:
            data_limite_br = "Não informada"

        # Mensagem ajustada contendo a data enviada pelo usuário
        numero_proto = context.get('numero_protocolo')
        message = f"O projeto {projeto.codigoCliente} recebeu: Protocolo {numero_proto} Vencimento: {data_limite_br})."
        url = f"/admin/projetos/{projeto.pk}/"

    elif evento == 'comprovante_adicionado':
        publico_alvo = 'admins'
        category = "COMPROVANTE_ENVIADO"
        title = "🧾 Novo Comprovante Recebido"
        message = f"O cliente {projeto.nomeTitular} enviou um comprovante de pagamento para o projeto {projeto.codigoCliente}."
        url = f"/admin/projetos/{projeto.pk}/"

    elif evento == 'vistoria_solicitada':
        publico_alvo = 'admins'
        category = "VISTORIA_SOLICITADA"
        title = "🚨 Solicitação de Vistoria"
        message = f"O usuário {sender.get_full_name() if sender else 'Cliente'} solicitou uma vistoria para o projeto {projeto.codigoCliente}."
        url = f"/admin/projetos/{projeto.pk}/"

    # --- 🆕 NOVOS EVENTOS: DOCUMENTOS DIRETOS DO USUÁRIO (Sem Projeto) ---
    elif evento == 'user_boleto_adicionado':
        publico_alvo = 'cliente'
        category = "BOLETO_ADICIONADO"
        title = "📄 Novo Boleto de Cadastro"
        message = "Um novo boleto de pagamento geral foi anexado ao seu perfil administrativo. Acesse para baixar."
        url = "/meus-documentos/"

    elif evento == 'user_comprovante_adicionado':
        publico_alvo = 'admins'
        category = "COMPROVANTE_ENVIADO"
        nome_cliente = cliente_direto.get_full_name() if cliente_direto else "Um cliente"
        title = "🧾 Novo Comprovante de Usuário"
        message = f"O usuário {nome_cliente} enviou um comprovante de pagamento direto no perfil."
        url = f"/admin/usuarios/{cliente_direto.pk}/" if cliente_direto else ""

    else:
        logger.error(f"Evento desconhecido: {evento}")
        return

    # Passa o 'cliente_direto' explicitamente para o roteador da Camada 2
    _rotear_e_salvar_notificacao(
        projeto=projeto,
        sender=sender,
        publico_alvo=publico_alvo,
        title=title,
        message=message,
        category=category,
        url=url,
        cliente=cliente_direto
    )

# ==============================================================================
# 🔵 CAMADA 4: FUNÇÕES ESPECIALIZADAS (As que as Views vão chamar de fato)
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

# --- Sem projeto atrelado, apenas user --- #
def notify_user_boleto_added(cliente, documento):
    """Acionada quando um admin insere um boleto direto na conta do usuário"""
    _construir_mensagem_notificacao(projeto=None, evento='user_boleto_adicionado', context={
        'cliente': cliente,
        'documento': documento
    })

def notify_user_comprovante_added(cliente, documento, cliente_remetente):
    """Acionada quando o cliente faz o upload de um comprovante no próprio perfil"""
    _construir_mensagem_notificacao(projeto=None, evento='user_comprovante_added', context={
        'cliente': cliente,
        'documento': documento
    }, sender=cliente_remetente)
    

# --- Destinadas aos Administradores ---
def notify_protocol_updated(projeto, numero_protocolo, data_limite):
    _construir_mensagem_notificacao(projeto, 'protocolo_atualizado', context={
        'numero_protocolo': numero_protocolo,
        'data_limite': data_limite
    })

def notify_comprovante_added(projeto, documento, cliente_remetente):
    _construir_mensagem_notificacao(projeto, 'comprovante_adicionado', context={'documento': documento}, sender=cliente_remetente)

def notify_inspection_requested(projeto, usuario_solicitante):
    _construir_mensagem_notificacao(projeto, 'vistoria_solicitada', context={}, sender=usuario_solicitante)