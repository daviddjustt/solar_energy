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
    Notifica o cliente quando um documento enviado por ele é recusado na análise.
    """
    cliente = projeto.created_by
    if not cliente: 
        return

    motivo = documento.rejection_reason or "Verifique detalhes na plataforma."
    
    try:
        # 1. Salva a notificação no banco de dados
        notif = Notification.objects.create(
            project=projeto, 
            recipient=cliente,
            title="❌ Documento Recusado",
            message=f"O documento do projeto {projeto.codigoCliente} foi recusado. Motivo: {motivo}",
            category="DOCUMENTO_RECUSADO"
        )
        
        # 2. Dispara o alerta apenas para a sala privada do cliente
        enviar_notificacao_websocket(f'user_notifications_{cliente.pk}', notif.title, notif.message)
        logger.info(f"Notificação de recusa enviada via WS para cliente {cliente.pk}.")
        
    except Exception as e:
        logger.error(f"Erro ao notificar recusa de documento: {str(e)}")


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