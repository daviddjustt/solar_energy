from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from solar.notifications.models import Notification
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

def enviar_notificacao_websocket(group_name, title, message):
    """Função auxiliar para reduzir repetição de código"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'send_notification',
            'data': {'title': title, 'message': message}
        }
    )

def processar_documento_rejeitado(projeto, documento):
    cliente = projeto.created_by
    if not cliente: return

    motivo = documento.rejection_reason or "Verifique detalhes na plataforma."
    try:
        # 1. Salva no banco
        notif = Notification.objects.create(
            project=projeto, recipient=cliente,
            title="❌ Documento Recusado",
            message=f"O documento do projeto {projeto.codigoCliente} foi recusado. Motivo: {motivo}",
            category="DOCUMENTO_RECUSADO"
        )
        # 2. Dispara o alerta para o cliente específico via WebSocket
        enviar_notificacao_websocket(f'user_notifications_{cliente.pk}', notif.title, notif.message)
        logger.info(f"Notificação enviada via WS para cliente {cliente.id}.")
    except Exception as e:
        logger.error(f"Erro: {str(e)}")

def processar_boleto_adicionado(cliente, documento):
    """Notifica o cliente específico que um boleto foi gerado para ele."""
    try:
        # 1. Salva no banco de dados para o histórico do cliente
        notif = Notification.objects.create(
            recipient=cliente,
            title="Novo Boleto Disponível",
            message="Um novo boleto de pagamento foi adicionado à sua conta. Acesse seus documentos para visualizar.",
            category="BOLETO_ADICIONADO"
        )
        
        # 2. Dispara o alerta em tempo real para a sala privada do cliente
        enviar_notificacao_websocket(
            f'user_notifications_{cliente.pk}', 
            notif.title, 
            notif.message
        )
        logger.info(f"Notificação de boleto enviada via WS para cliente {cliente.email}.")
    except Exception as e:
        logger.error(f"Erro ao processar notificação de boleto: {str(e)}")

def processar_boleto_adicionado(projeto, documento):
    """Notifica o cliente que um boleto foi gerado para o projeto dele."""
    cliente = projeto.created_by
    if not cliente: 
        return

    try:
        # 1. Salva no banco (Histórico do cliente)
        notif = Notification.objects.create(
            project=projeto,
            recipient=cliente,
            title="Novo Boleto Disponível",
            message=f"Um novo boleto de pagamento foi adicionado ao projeto {projeto.codigoCliente}. Acesse a aba de documentos para visualizar.",
            category="BOLETO_ADICIONADO"
        )
        
        # 2. Dispara o alerta no WebSocket do cliente
        # Lembre-se: usamos .pk conforme ajustamos anteriormente!
        enviar_notificacao_websocket(f'user_notifications_{cliente.pk}', notif.title, notif.message)
        logger.info(f"Notificação de boleto enviada via WS para cliente ID {cliente.pk}.")
    except Exception as e:
        logger.error(f"Erro ao processar notificação de boleto: {str(e)}")


def processar_comprovante_adicionado(projeto, documento, cliente_remetente):
    """Notifica TODOS os administradores que um comprovante foi enviado."""
    try:
        admins = User.objects.filter(is_admin=True)
        
        # 1. Cria notificações em lote para os admins
        notificacoes_para_criar = [
            Notification(
                project=projeto,
                sender=cliente_remetente,
                recipient=admin,
                title="Novo Comprovante Recebido",
                message=f"O cliente {projeto.nomeTitular} enviou um comprovante de pagamento para o projeto {projeto.codigoCliente}.",
                category="COMPROVANTE_ENVIADO"
            )
            for admin in admins
        ]
        
        if notificacoes_para_criar:
            Notification.objects.bulk_create(notificacoes_para_criar)
            
            # 2. Dispara na sala "Administradores" do WebSocket
            enviar_notificacao_websocket(
                "Administradores", 
                "🧾 Novo Comprovante Recebido", 
                f"O cliente {projeto.nomeTitular} enviou um comprovante de pagamento para o projeto {projeto.codigoCliente}."
            )
            logger.info(f"Notificação de comprovante enviada via WS para os Admins.")
    except Exception as e:
        logger.error(f"Erro ao processar notificação de comprovante: {str(e)}")
        
        
def processar_comprovante_adicionado(cliente, documento):
    """Notifica TODOS os administradores que um cliente enviou um comprovante."""
    try:
        admins = User.objects.filter(is_admin=True)
        
        # 1. Cria as notificações em lote no banco para todos os administradores
        notificacoes_para_criar = [
            Notification(
                sender=cliente,
                recipient=admin,
                title="Novo Comprovante Recebido",
                message=f"O cliente {cliente.name or cliente.email} enviou um novo comprovante de pagamento.",
                category="COMPROVANTE_ENVIADO"
            )
            for admin in admins
        ]
        
        if notificacoes_para_criar:
            Notification.objects.bulk_create(notificacoes_para_criar)
            
            # 2. Dispara o alerta na sala "Megafone" dos Administradores
            enviar_notificacao_websocket(
                "Administradores", 
                "Novo Comprovante Recebido", 
                f"O cliente {cliente.name or cliente.email} enviou um novo comprovante de pagamento."
            )
            logger.info(f"Notificação de comprovante enviada via WS para os Admins.")
    except Exception as e:
        logger.error(f"Erro ao processar notificação de comprovante: {str(e)}")
        
def processar_solicitacao_vistoria(projeto, cliente_solicitante):
    """
    Cria notificações em lote para administradores e dispara um alerta WebSocket.
    """
    admins = User.objects.filter(is_admin=True)
    
    # 1. Preparar a lista de notificações para criação em lote
    notificacoes_para_criar = [
        Notification(
            project=projeto,
            sender=cliente_solicitante,
            recipient=admin,
            title="📋 Nova Vistoria Solicitada",
            message=f"Cliente {projeto.nomeTitular} solicitou vistoria.",
            category="SOLICITACAO_VISTORIA"
        )
        for admin in admins
    ]
    
    if notificacoes_para_criar:
        # 2. Persistência no Banco de Dados
        Notification.objects.bulk_create(notificacoes_para_criar)
        
        # 3. Disparo WebSocket (Notifica o grupo de Administradores no Redis)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "Administradores",  # Nome do grupo registrado no seu Consumer
            {
                "type": "send_notification",
                "data": {
                    "title": "Nova Vistoria Solicitada",
                    "message": f"O cliente {projeto.nomeTitular} solicitou uma vistoria para o projeto {projeto.codigoCliente}.",
                    "url": f"/admin/projetos/{projeto.pk}/" # Link para o admin verificar
                }
            }
        )