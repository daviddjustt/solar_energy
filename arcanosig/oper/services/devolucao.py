from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from arcanosig.oper.models import (
    CautelaIndividual,
    ItemCautela,
    StatusEquipamento,
    TipoNotificacao
)
from arcanosig.oper.services.notifications import NotificacaoService
from arcanosig.oper.services.cautela_service import CautelaService


class DevolucaoService:
    """
    Serviço para gerenciar devolução de equipamentos.
    """


    @staticmethod
    def registrar_devolucao_item(item_id, status=StatusEquipamento.EM_CONDICOES, descricao_danos="", user=None):
        """
        Registra a devolução de um item de cautela.
        """
        try:
            item = ItemCautela.objects.get(id=item_id)

            # Verificar se o item já foi devolvido
            if item.data_devolucao:
                return False, _("Este item já foi devolvido.")

            with transaction.atomic():
                # Registrar a devolução
                data_devolucao = timezone.now()
                item.data_devolucao = data_devolucao
                item.status_equipamento = status
                item.descricao_danos = descricao_danos.upper() if descricao_danos else ""
                item.protocolo_devolucao = f"DEV-{item.id}-{data_devolucao.strftime('%Y%m%d%H%M')}"
                item.devolucao_confirmada = True
                item.save()

                # Criar notificação de devolução (e já marca como lida)
                notificacao = NotificacaoService.criar_notificacao_devolucao_item(item)
                if notificacao:
                    notificacao.lida = True
                    notificacao.data_leitura = data_devolucao
                    notificacao.save(update_fields=['lida', 'data_leitura'])

                # Se o item estiver danificado, criar notificação específica
                if status in [StatusEquipamento.DANIFICADO, StatusEquipamento.INOPERANTE, StatusEquipamento.EXTRAVIADO]:
                    NotificacaoService.criar_notificacao_item_danificado(item)

                # Verificar se a cautela está completamente devolvida
                # Passar emitir_evento=False para evitar duplicação de notificações
                CautelaService.verificar_devolucao_completa(item.cautela, emitir_evento=False)

                return True, _("Devolução registrada com sucesso.")

        except ItemCautela.DoesNotExist:
            return False, _("Item não encontrado.")
        except Exception as e:
            return False, str(e)

    @staticmethod
    def devolver_cautela_completa(cautela_id, observacao="", user=None):
        """
        Devolve todos os itens de uma cautela de uma vez.
        """
        try:
            cautela = CautelaIndividual.objects.get(id=cautela_id)

            # Verificar se a cautela já foi devolvida
            if cautela.data_devolucao:
                return False, _("Esta cautela já foi devolvida.")

            with transaction.atomic():
                # Obter todos os itens não devolvidos
                itens_pendentes = ItemCautela.objects.filter(
                    cautela=cautela,
                    data_devolucao__isnull=True
                )

                if not itens_pendentes.exists():
                    return False, _("Não há itens pendentes de devolução nesta cautela.")

                data_devolucao = timezone.now()

                # Devolver todos os itens pendentes
                for item in itens_pendentes:
                    item.data_devolucao = data_devolucao
                    item.status_equipamento = StatusEquipamento.EM_CONDICOES
                    item.protocolo_devolucao = f"DEV-BULK-{cautela.id}-{data_devolucao.strftime('%Y%m%d%H%M')}"
                    item.devolucao_confirmada = True
                    item.save()

                # Marcar a cautela como devolvida
                cautela.data_devolucao = data_devolucao
                cautela.observacao_devolucao = observacao.upper() if observacao else _("Devolução em massa de todos os itens.")
                cautela.save(update_fields=['data_devolucao', 'observacao_devolucao'])

                # Criar notificação de devolução completa e já marcar como lida
                link = NotificacaoService.gerar_link_cautela(cautela.id)
                notificacao = NotificacaoService.criar_notificacao(
                    usuario=cautela.policial,
                    titulo=_("Cautela devolvida"),
                    mensagem=_(f"Todos os itens da cautela (Protocolo: {cautela.protocolo_aceite}) foram devolvidos."),
                    tipo=TipoNotificacao.DEVOLUCAO_CONFIRMADA,
                    link=link
                )

                if notificacao:
                    notificacao.lida = True
                    notificacao.data_leitura = data_devolucao
                    notificacao.save(update_fields=['lida', 'data_leitura'])

                return True, _("Cautela devolvida com sucesso.")

        except CautelaIndividual.DoesNotExist:
            return False, _("Cautela não encontrada.")
        except Exception as e:
            return False, str(e)

    @staticmethod
    def relatar_danos_equipamento(item_id, status, descricao_danos, user=None):
        """
        Registra danos em um equipamento já devolvido.

        Args:
            item_id: ID do ItemCautela
            status: Novo status do equipamento
            descricao_danos: Descrição detalhada dos danos
            user: Usuário que está relatando os danos

        Returns:
            Tupla com (sucesso, mensagem)
        """
        try:
            item = ItemCautela.objects.get(id=item_id)

            # Verificar se o item foi devolvido
            if not item.data_devolucao:
                return False, _("Este item ainda não foi devolvido e não pode ter danos reportados.")

            with transaction.atomic():
                # Registrar os danos
                old_status = item.status_equipamento
                item.status_equipamento = status
                item.descricao_danos = descricao_danos.upper() if descricao_danos else ""

                # Verificar se deve notificar (status mudou para danificado/inoperante)
                should_notify = (
                    old_status not in [StatusEquipamento.DANIFICADO, StatusEquipamento.INOPERANTE, StatusEquipamento.EXTRAVIADO] and
                    status in [StatusEquipamento.DANIFICADO, StatusEquipamento.INOPERANTE, StatusEquipamento.EXTRAVIADO]
                )

                item.save()

                # Criar notificação sobre danos, se necessário
                if should_notify:
                    NotificacaoService.criar_notificacao_item_danificado(item)

                return True, _("Danos reportados com sucesso.")

        except ItemCautela.DoesNotExist:
            return False, _("Item não encontrado.")
        except Exception as e:
            return False, str(e)
