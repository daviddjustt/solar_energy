# solar/documents/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import ClientProject, AndamentoDoProjeto
from solar.users.email import StatusProjetoChangedEmail
import logging

logger = logging.getLogger(__name__)

# Lista de status que devem disparar o e-mail
STATUS_QUE_GERAM_EMAIL = [
    AndamentoDoProjeto.ANALISE_DE_PAGAMENTOS,
    AndamentoDoProjeto.PAGAMENTO_TRT_ART,
    AndamentoDoProjeto.PAGAMENTO_DO_PROJETO,
    AndamentoDoProjeto.ANALISE_TECNICA,
    AndamentoDoProjeto.APROVADO,
    AndamentoDoProjeto.REPROVADO,
    AndamentoDoProjeto.VISTORIA,
    AndamentoDoProjeto.CONCLUIDO,
]

@receiver(pre_save, sender=ClientProject)
def notificar_mudanca_status_projeto(sender, instance, **kwargs):
    # Se for um projeto novo (ainda não tem ID), não disparamos mudança de status
    if not instance.id:
        return

    try:
        # Busca o projeto como ele está atualmente no banco de dados
        projeto_antigo = ClientProject.objects.get(id=instance.id)
    except ClientProject.DoesNotExist:
        return

    # Verifica se o status mudou E se o novo status está na lista de alertas
    if projeto_antigo.status != instance.status and instance.status in STATUS_QUE_GERAM_EMAIL:
        # Verifica se o projeto tem um usuário vinculado e se ele tem email
        if instance.created_by and instance.created_by.email:
            try:
                # Dispara o email
                StatusProjetoChangedEmail(
                    context={
                        'projeto': instance,
                        'status_antigo': projeto_antigo.get_status_display(),
                        'status_novo': instance.get_status_display()
                    }
                ).send(to=[instance.created_by.email])
                
                logger.info(f"Signal disparou email de mudança de status para {instance.created_by.email}. Projeto: {instance.codigoCliente}")
            except Exception as e:
                logger.error(f"Erro ao enviar email de mudança de status do projeto {instance.id}: {str(e)}")