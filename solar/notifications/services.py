import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from solar.notifications.models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()

# ==========================================
# 🔧 FUNÇÃO AUXILIAR GLOBAL
# ==========================================
def enviar_notificacao_websocket(group_name, title, message, url=""):
    """
    Função auxiliar para centralizar e reduzir a repetição do código de disparo do WebSocket.
    Envia o dicionário exato que o Consumer espera receber.
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'send_notification',
            'data': {
                'title': title, 
                'message': message,
                'url': url  # Adicionado suporte para link de redirecionamento (opcional)
            }
        }
    )


# ==========================================
# 📄 FLUXO DE DOCUMENTOS
# ==========================================
def processar_documento_rejeitado(projeto, documento):
    """
    Notifica o cliente quando um documento ou comprovante é recusado.
    A mensagem se adapta automaticamente ao tipo de arquivo.
    """
    cliente = projeto.created_by
    if not cliente: 
        return

    motivo = documento.rejection_reason or "Verifique os detalhes na plataforma."
    
    # 🧠 Lógica inteligente: O texto muda se for um comprovante de pagamento
    if documento.document_type == 'comprovante_de_pagamento':
        titulo = "❌ Comprovante Recusado"
        mensagem = f"O comprovante de pagamento do projeto {projeto.codigoCliente} não foi aceito. Motivo: {motivo}"
        categoria = "COMPROVANTE_RECUSADO"
    else:
        # Pega o nome amigável do documento (ex: "Contrato Social" em vez de "contrato_social")
        nome_doc = documento.get_document_type_display() or "documento"
        titulo = "❌ Documento Recusado"
        mensagem = f"O seu arquivo '{nome_doc}' do projeto {projeto.codigoCliente} foi recusado. Motivo: {motivo}"
        categoria = "DOCUMENTO_RECUSADO"

    try:
        # 1. Salva a notificação no banco de dados
        notif = Notification.objects.create(
            project=projeto, 
            recipient=cliente,
            title=titulo,
            message=mensagem,
            category=categoria
        )
        
        # 2. Dispara o alerta via WebSocket
        enviar_notificacao_websocket(f'user_notifications_{cliente.pk}', notif.title, notif.message)
        logger.info(f"Notificação de recusa ({categoria}) enviada via WS para cliente {cliente.pk}.")
        
    except Exception as e:
        logger.error(f"Erro ao notificar recusa de documento: {str(e)}")


def processar_documento_aprovado(projeto, documento):
    """
    Notifica o cliente apenas quando documentos cruciais (como comprovantes) são aprovados.
    """
    cliente = projeto.created_by
    if not cliente: 
        return

    # Só queremos incomodar o cliente com uma notificação feliz se for o pagamento.
    # (Se você quiser notificar TODO documento aprovado, basta remover este 'if')
    if documento.document_type == 'comprovante_de_pagamento':
        titulo = "✅ Pagamento Aprovado!"
        mensagem = f"O seu comprovante de pagamento para o projeto {projeto.codigoCliente} foi analisado e aprovado com sucesso."
        categoria = "COMPROVANTE_APROVADO"
        
        try:
            notif = Notification.objects.create(
                project=projeto, 
                recipient=cliente,
                title=titulo, 
                message=mensagem, 
                category=categoria
            )
            enviar_notificacao_websocket(f'user_notifications_{cliente.pk}', notif.title, notif.message)
            logger.info(f"Notificação de aprovação de pagamento enviada via WS para cliente {cliente.pk}.")
        except Exception as e:
            logger.error(f"Erro ao notificar aprovação de comprovante: {str(e)}")
            
def processar_boleto_adicionado(projeto, documento):
    """
    Notifica o cliente que a empresa gerou um boleto e anexou ao projeto dele.
    """
    cliente = projeto.created_by
    if not cliente: 
        return

    try:
        # 1. Salva no banco (Histórico de notificações do cliente)
        notif = Notification.objects.create(
            project=projeto,
            recipient=cliente,
            title="📄 Novo Boleto Disponível",
            message=f"Um novo boleto de pagamento foi adicionado ao projeto {projeto.codigoCliente}. Acesse a aba de documentos para visualizar.",
            category="BOLETO_ADICIONADO"
        )
        
        # 2. Dispara o alerta no WebSocket exclusivo do cliente
        enviar_notificacao_websocket(f'user_notifications_{cliente.pk}', notif.title, notif.message)
        logger.info(f"Notificação de boleto enviada via WS para cliente ID {cliente.pk}.")
        
    except Exception as e:
        logger.error(f"Erro ao processar notificação de boleto: {str(e)}")


def processar_comprovante_adicionado(projeto, documento, cliente_remetente):
    """
    Notifica TODOS os administradores que o cliente enviou um comprovante de pagamento.
    """
    try:
        # Filtra a equipe de diretores/administradores
        admins = User.objects.filter(is_admin=True)
        
        titulo_notificacao = "🧾 Novo Comprovante Recebido"
        mensagem_notificacao = f"O cliente {projeto.nomeTitular} enviou um comprovante de pagamento para o projeto {projeto.codigoCliente}."
        
        # 1. Cria notificações em lote para todos os administradores simultaneamente
        notificacoes_para_criar = [
            Notification(
                project=projeto,
                sender=cliente_remetente,
                recipient=admin,
                title=titulo_notificacao,
                message=mensagem_notificacao,
                category="COMPROVANTE_ENVIADO"
            )
            for admin in admins
        ]
        
        if notificacoes_para_criar:
            Notification.objects.bulk_create(notificacoes_para_criar) # Escrita otimizada no banco
            
            # 2. Dispara o alerta geral na sala "Administradores"
            enviar_notificacao_websocket("Administradores", titulo_notificacao, mensagem_notificacao)
            logger.info(f"Notificação de comprovante enviada via WS para os Admins.")
            
    except Exception as e:
        logger.error(f"Erro ao processar notificação de comprovante: {str(e)}")


# ==========================================
# 📋 FLUXO DE VISTORIA
# ==========================================
def processar_solicitacao_vistoria(projeto, cliente_solicitante):
    """
    Cria notificações em lote para administradores quando o cliente solicita a vistoria.
    """
    try:
        admins = User.objects.filter(is_admin=True)
        
        titulo_notificacao = "📋 Nova Vistoria Solicitada"
        mensagem_notificacao = f"O cliente {projeto.nomeTitular} solicitou uma vistoria para o projeto {projeto.codigoCliente}."
        
        # 1. Prepara a lista de notificações para criação em lote
        notificacoes_para_criar = [
            Notification(
                project=projeto,
                sender=cliente_solicitante,
                recipient=admin,
                title=titulo_notificacao,
                message=mensagem_notificacao,
                category="SOLICITACAO_VISTORIA"
            )
            for admin in admins
        ]
        
        if notificacoes_para_criar:
            # 2. Persistência no Banco de Dados
            Notification.objects.bulk_create(notificacoes_para_criar)
            
            # 3. Disparo WebSocket reaproveitando a nossa função auxiliar global
            # Note que passamos a URL para que o Front-end possa criar um botão clicável
            enviar_notificacao_websocket(
                group_name="Administradores",
                title=titulo_notificacao,
                message=mensagem_notificacao,
                url=f"/admin/projetos/{projeto.pk}/"
            )
            logger.info(f"Notificação de vistoria enviada via WS para os Admins.")
            
    except Exception as e:
        logger.error(f"Erro ao processar solicitação de vistoria: {str(e)}")