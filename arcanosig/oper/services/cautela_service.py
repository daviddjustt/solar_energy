from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid

from arcanosig.oper.models import (
    CautelaIndividual,
    ItemCautela,
    AceiteCautela,
    StatusEquipamento,
    StatusAceite,
)

from arcanosig.oper.models.notificacao import Notificacao
from arcanosig.oper.models.enums import TipoNotificacao

class CautelaService:
    """
    Serviço centralizado para gerenciar todo o fluxo de cautelas.
    Aplica o princípio de responsabilidade única e centraliza as regras de negócio.
    """

    @staticmethod
    def criar_cautela(policial, guarnicao, itens=None):
        """
        Cria uma nova cautela com fluxo transacional completo.

        Args:
            policial: Objeto User (policial)
            guarnicao: Objeto Guarnicao
            itens: Lista de dicionários com informações dos itens

        Returns:
            Tuple (success, message, cautela_obj)
        """
        try:
            with transaction.atomic():
                # Validações
                if CautelaIndividual.objects.filter(
                    policial=policial,
                    data_devolucao__isnull=True
                ).exists():
                    return False, _("O policial já possui uma cautela ativa."), None

                # Verificar se o policial é membro da guarnição
                is_member = guarnicao.membros.filter(id=policial.id).exists()
                if not is_member:
                    return False, _("O policial deve ser membro da guarnição para receber uma cautela."), None

                # Verificar se a operação está ativa
                if not guarnicao.operacao.is_active:
                    return False, _("Cautelas só podem ser criadas para operações ativas."), None

                # Criar cautela
                policial_id_short = str(policial.id).split('-')[0]
                protocolo = f"CAUT-{policial_id_short}-{timezone.now().strftime('%Y%m%d%H%M')}"
                cautela = CautelaIndividual.objects.create(
                    policial=policial,
                    guarnicao=guarnicao,
                    data_entrega=timezone.now(),
                    protocolo_aceite=protocolo
                )

                # Criar apenas UM aceite
                aceite = AceiteCautela.objects.create(
                    cautela=cautela,
                    protocolo=protocolo,  # Usa o MESMO protocolo da cautela
                    status=StatusAceite.PENDENTE
                )

                # Adicionar itens
                if itens:
                    for item_data in itens:
                        ItemCautela.objects.create(
                            cautela=cautela,
                            tipo_equipamento=item_data.get('tipo_equipamento'),
                            numero_serie=item_data.get('numero_serie', ''),
                            quantidade=item_data.get('quantidade', 1),
                            observacao=item_data.get('observacao', '')
                        )

                # Emitir evento de cautela criada (será capturado pelo sistema de notificação)
                from arcanosig.oper.services.notification_hub import NotificationHub
                NotificationHub.emit_event('cautela_criada', cautela=cautela, aceite=aceite)

                return True, _("Cautela criada com sucesso."), cautela

        except Exception as e:
            return False, str(e), None

    @staticmethod
    def processar_aceite(protocolo, usuario, ip_address=None, observacao=None):
        """
        Processa o aceite de uma cautela pelo policial.
        """
        try:
            with transaction.atomic():
                # Localizar o aceite pelo protocolo
                aceite = AceiteCautela.objects.select_related('cautela').get(protocolo=protocolo)

                # Validações
                if aceite.status != StatusAceite.PENDENTE:
                    return False, _("Este aceite já foi processado.")

                # Verificar permissão - apenas o policial responsável pode aceitar
                if usuario.id != aceite.cautela.policial.id and not (usuario.is_admin or usuario.is_superuser):
                    return False, _("Apenas o policial responsável pode confirmar o aceite da cautela.")

                # Confirmar aceite
                aceite.status = StatusAceite.CONFIRMADO
                aceite.data_aceite = timezone.now()
                aceite.ip_aceite = ip_address
                aceite.observacao = observacao or ""
                aceite.save()

                # Atualizar cautela
                cautela = aceite.cautela
                cautela.aceite_status = aceite.status
                cautela.data_hora_aceite = aceite.data_aceite
                cautela.save(update_fields=['aceite_status', 'data_hora_aceite'])

                # ADICIONAR ESTE BLOCO: Marcar notificação de cautela pendente como lida
                Notificacao.objects.filter(
                    usuario=cautela.policial,
                    tipo=TipoNotificacao.CAUTELA_PENDENTE,
                    link__contains=str(cautela.id),
                    lida=False
                ).update(
                    lida=True,
                    data_leitura=aceite.data_aceite
                )

                # Emitir evento (para notificação)
                from arcanosig.oper.services.notification_hub import NotificationHub
                NotificationHub.emit_event(
                    'aceite_confirmado',
                    aceite=aceite,
                    cautela=cautela,
                    usuario_acao=usuario
                )

                return True, _("Aceite confirmado com sucesso")

        except AceiteCautela.DoesNotExist:
            return False, _("Aceite não encontrado.")
        except Exception as e:
            return False, str(e)


    @staticmethod
    def devolver_item(item_id, user, status=StatusEquipamento.EM_CONDICOES, descricao_danos=""):
        """
        Registra a devolução de um item específico.
        """
        try:
            with transaction.atomic():
                # Buscar o item
                item = ItemCautela.objects.select_related('cautela').get(id=item_id)

                # Verificar se já foi devolvido
                if item.data_devolucao:
                    return False, _("Este item já foi devolvido.")

                # Registrar devolução
                item.data_devolucao = timezone.now()
                item.status_equipamento = status
                item.descricao_danos = descricao_danos or ""
                item.protocolo_devolucao = f"DEV-{uuid.uuid4().hex[:8].upper()}"
                item.devolucao_confirmada = True
                item.save()

                # Verificar se a cautela está completamente devolvida
                todos_devolvidos = not ItemCautela.objects.filter(
                    cautela=item.cautela,
                    data_devolucao__isnull=True
                ).exists()

                # Se todos estão devolvidos, finalizar a cautela
                if todos_devolvidos:
                    item.cautela.data_devolucao = timezone.now()
                    item.cautela.observacao_devolucao = _("Todos os itens foram devolvidos.")
                    item.cautela.save(update_fields=['data_devolucao', 'observacao_devolucao'])

                    # Emitir evento para cautela completamente devolvida
                    from arcanosig.oper.services.notification_hub import NotificationHub
                    NotificationHub.emit_event('cautela_devolvida', cautela=item.cautela, usuario_acao=user)

                    # Não emitir evento para item individual neste caso
                    return True, _("Item devolvido com sucesso. Cautela completamente devolvida.")
                else:
                    # Emitir evento para item devolvido
                    from arcanosig.oper.services.notification_hub import NotificationHub
                    NotificationHub.emit_event(
                        'item_devolvido',
                        item=item,
                        cautela=item.cautela,
                        com_danos=(status != StatusEquipamento.EM_CONDICOES),
                        usuario_acao=user
                    )

                    return True, _("Item devolvido com sucesso.")

        except ItemCautela.DoesNotExist:
            return False, _("Item não encontrado.")
        except Exception as e:
            return False, str(e)

    @staticmethod
    def devolver_cautela_completa(cautela_id, user, observacao=""):
        """
        Devolve todos os itens de uma cautela de uma vez.

        Args:
            cautela_id: ID da cautela
            user: Usuário realizando a devolução
            observacao: Observação opcional

        Returns:
            Tuple (success, message)
        """
        try:
            with transaction.atomic():
                # Buscar cautela
                cautela = CautelaIndividual.objects.get(id=cautela_id)

                # Verificar se já foi devolvida
                if cautela.data_devolucao:
                    return False, _("Esta cautela já foi devolvida.")

                # Buscar itens não devolvidos
                itens = ItemCautela.objects.filter(
                    cautela=cautela,
                    data_devolucao__isnull=True
                )

                if not itens.exists():
                    return False, _("Não há itens pendentes de devolução.")

                # Devolver todos os itens
                timestamp = timezone.now()
                protocolo_base = f"DEV-MASSA-{cautela.id}-{timestamp.strftime('%Y%m%d%H%M')}"

                for i, item in enumerate(itens):
                    item.data_devolucao = timestamp
                    item.status_equipamento = StatusEquipamento.EM_CONDICOES
                    item.protocolo_devolucao = f"{protocolo_base}-{i+1}"
                    item.devolucao_confirmada = True
                    item.save()

                # Finalizar a cautela
                cautela.data_devolucao = timestamp
                cautela.observacao_devolucao = observacao or _("Devolução em massa de todos os itens.")
                cautela.save(update_fields=['data_devolucao', 'observacao_devolucao'])

                # Emitir evento uma única vez
                from arcanosig.oper.services.notification_hub import NotificationHub
                NotificationHub.emit_event('cautela_devolvida', cautela=cautela, usuario_acao=user)

                return True, _("Cautela devolvida com sucesso.")

        except CautelaIndividual.DoesNotExist:
            return False, _("Cautela não encontrada.")
        except Exception as e:
            return False, str(e)



    @staticmethod
    def verificar_devolucao_completa(cautela, atualizar=True, emitir_evento=True):
        """
        Verifica se todos os itens de uma cautela foram devolvidos.
        Se todos estiverem devolvidos e atualizar=True, finaliza a cautela.

        Args:
            cautela: Objeto CautelaIndividual
            atualizar: Boolean indicando se deve atualizar a cautela se estiver completa
            emitir_evento: Boolean indicando se deve emitir eventos de notificação

        Returns:
            Boolean indicando se a cautela está completamente devolvida
        """
        # Verifica se a cautela já está devolvida
        if cautela.data_devolucao:
            return True

        # Verificar se todos os itens foram devolvidos
        itens_pendentes = ItemCautela.objects.filter(
            cautela=cautela,
            data_devolucao__isnull=True
        ).exists()

        # Se não há itens pendentes e atualizar=True, finaliza a cautela
        if not itens_pendentes and atualizar:
            cautela.data_devolucao = timezone.now()
            cautela.observacao_devolucao = _("Todos os itens foram devolvidos.")
            cautela.save(update_fields=['data_devolucao', 'observacao_devolucao'])

            # Emitir evento para cautela completamente devolvida somente se solicitado
            if emitir_evento:
                from arcanosig.oper.services.notification_hub import NotificationHub
                NotificationHub.emit_event('cautela_devolvida', cautela=cautela)

        return not itens_pendentes
