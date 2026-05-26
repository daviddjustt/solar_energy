# solar/documents/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import ClientProject, AndamentoDoProjeto, ProjectDocument
from solar.users.email import StatusProjetoChangedEmail, DocumentRejectedEmail
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


@receiver(pre_save, sender=ProjectDocument)
def notificar_documento_rejeitado(sender, instance, **kwargs):
    # Se for um documento novo (recém criado), ignoramos, pois ele entra em 'IN_ANALYSIS'
    if not instance.id:
        return

    try:
        # Busca o estado atual do documento no banco de dados
        documento_antigo = ProjectDocument.objects.get(id=instance.id)
    except ProjectDocument.DoesNotExist:
        return

    # A mágica acontece aqui: O status anterior era diferente de REJECTED e o novo é REJECTED?
    if documento_antigo.status != instance.status and instance.status == ProjectDocument.STATUS_REJECTED:
        projeto = instance.project
        
        # Verifica se o documento está vinculado a um projeto e se o dono tem e-mail
        if projeto and projeto.created_by and projeto.created_by.email:
            try:
                # Dispara o email
                DocumentRejectedEmail(
                    context={
                        'documento': instance,
                        'projeto': projeto,
                        # Se o analista esqueceu de preencher o motivo, evitamos enviar vazio
                        'motivo': instance.rejection_reason or "Por favor, acesse a plataforma para verificar os detalhes ou entre em contato com o suporte."
                    }
                ).send(to=[projeto.created_by.email])
                
                logger.info(f"Signal disparou email de rejeição de documento para {projeto.created_by.email}. Projeto: {projeto.codigoCliente}")
            except Exception as e:
                logger.error(f"Erro ao enviar email de rejeição de documento {instance.id}: {str(e)}")

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