from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from solar.notifications.models import Notification

User = get_user_model()

# solar/notifications/services.py
import logging
from django.contrib.auth import get_user_model
from solar.notifications.models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()

def processar_documento_rejeitado(projeto, documento):
    """
    Cria uma notificação interna (sistema/stream) para o cliente.
    """
    cliente = projeto.created_by
    if not cliente:
        return

    motivo_rejeicao = documento.rejection_reason or "Por favor, acesse a plataforma para verificar os detalhes ou entre em contato com o suporte."
    try:
        Notification.objects.create(
            project=projeto,
            sender=None,  # Fica nulo pois foi uma ação automatizada do sistema/analista
            recipient=cliente,
            title=f"❌ Documento Recusado: {'Verificar arquivo'}",
            message=f"O documento do seu projeto {projeto.codigoCliente} foi recusado. Motivo: {motivo_rejeicao}",
            category="DOCUMENTO_RECUSADO"
        )
        logger.info(f"Notificação de documento rejeitado salva no banco para o cliente {cliente.id}.")
    except Exception as e:
        logger.error(f"Erro ao criar notificação de documento rejeitado no banco: {str(e)}")
        
def processar_solicitacao_vistoria(projeto, cliente_solicitante):
    """
    Orquestra as regras de negócio quando uma vistoria é solicitada:
    Notifica todos os administradores do sistema em lote.
    """
    
    # ─── 2. NOTIFICAÇÃO EM LOTE PARA OS ADMINS ───
    # Buscamos todos os usuários que possuem flags de administração ativa
    admins = User.objects.filter(is_admin=True) # ou use um grupo específico como Group.objects.get(name='Admin')
    
    # Criamos uma lista de objetos na memória para inserir de uma vez só (Bulk Create)
    notificacoes_para_criar = []
    
    for admin in admins:
        notificacoes_para_criar.append(
            Notification(
                project=projeto,
                sender=cliente_solicitante,
                recipient=admin,
                title="📋 Nova Vistoria Solicitada",
                message=f"O cliente {projeto.nomeTitular} solicitou uma vistoria para o projeto {projeto.codigoCliente}.",
                category="SOLICITACAO_VISTORIA"
            )
        )
    
    # Executa um único INSERT no banco com todas as notificações (Alta Performance)
    if notificacoes_para_criar:
        Notification.objects.bulk_create(notificacoes_para_criar)