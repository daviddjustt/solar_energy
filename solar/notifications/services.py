from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from solar.notifications.models import Notification

User = get_user_model()

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