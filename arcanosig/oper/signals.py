from django.db.models.signals import post_save
from django.dispatch import receiver
from arcanosig.oper.models.cautela import ItemCautela
from arcanosig.oper.services.cautela_service import CautelaService
import logging

logger = logging.getLogger(__name__)

@receiver(
    post_save,
    sender=ItemCautela,
    dispatch_uid='itemcautela_update_cautela_on_item_return'
)
def update_cautela_on_item_return(sender, instance, created, update_fields, **kwargs):
    """
    Ao salvar um ItemCautela, se o campo data_devolucao acabou de ser setado,
    dispara a verificação da devolução completa na CautelaIndividual associada.
    """
    # 1) se for create, não temos nada a verificar
    if created:
        return

    # 2) se veio update_fields e não incluiu data_devolucao, pula
    if update_fields and 'data_devolucao' not in update_fields:
        return

    # 3) só continua se data_devolucao estiver preenchido e existir foreign key
    if not instance.data_devolucao or not instance.cautela_id:
        return

    # 4) chama o serviço, protegendo de exceções
    try:
        CautelaService.verificar_devolucao_completa(
            cautela=instance.cautela,
            atualizar=True,
            emitir_evento=False
        )
    except Exception as e:
        logger.error(
            f"Falha ao verificar devolução completa da cautela "
            f"{instance.cautela_id} (item {instance.id}): {e}"
        )
