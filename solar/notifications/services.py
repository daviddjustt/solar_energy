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
        enviar_notificacao_websocket(f'user_notifications_{cliente.id}', notif.title, notif.message)
        logger.info(f"Notificação enviada via WS para cliente {cliente.id}.")
    except Exception as e:
        logger.error(f"Erro: {str(e)}")

def processar_solicitacao_vistoria(projeto, cliente_solicitante):
    admins = User.objects.filter(is_admin=True)
    notificacoes_para_criar = []
    
    for admin in admins:
        notificacoes_para_criar.append(
            Notification(
                project=projeto, sender=cliente_solicitante, recipient=admin,
                title="📋 Nova Vistoria Solicitada",
                message=f"Cliente {projeto.nomeTitular} solicitou vistoria.",
                category="SOLICITACAO_VISTORIA"
            )
        )
    
    if notificacoes_para_criar:
        Notification.objects.bulk_create(notificacoes_para_criar)
        
        # Dispara aviso para o grupo de admins
        # Nota: Você precisaria que os admins estivessem conectados a um grupo chamado 'admin_notifications'
        enviar_notificacao_websocket("Administradores", "Nova Vistoria", "Uma nova vistoria foi solicitada.")