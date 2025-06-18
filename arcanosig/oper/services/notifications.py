from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from arcanosig.oper.models.notificacao import Notificacao
from arcanosig.oper.models.enums import TipoNotificacao, StatusAceite, StatusEquipamento


class NotificacaoService:
    """
    Serviço para gerenciar notificações no sistema.
    Centraliza toda a lógica de criação de notificações para garantir consistência.
    """

    @staticmethod
    def criar_notificacao(usuario, titulo, mensagem, tipo, link=""):
        """
        Cria uma nova notificação para um usuário.

        Args:
            usuario: Objeto User
            titulo: Título da notificação
            mensagem: Texto da notificação
            tipo: TipoNotificacao (enum da classe Notificacao)
            link: Link opcional para detalhes

        Returns:
            Objeto Notificacao criado
        """
        if not usuario:
            # Fail fast se o usuário não for fornecido
            return None

        return Notificacao.objects.create(
            usuario=usuario,
            titulo=titulo,
            mensagem=mensagem,
            tipo=tipo,
            link=link
        )

    @staticmethod
    def gerar_link_cautela(cautela_id):
        """
        Gera um link para a página de detalhes da cautela.

        Args:
            cautela_id: ID da cautela

        Returns:
            Link para a página de detalhes
        """
        # Idealmente usaríamos reverse(), mas mantendo consistência com código existente
        return f"/cautelas/detalhe/{cautela_id}/"

    @staticmethod
    def gerar_link_item(item_id):
        """
        Gera um link para a página de detalhes do item.

        Args:
            item_id: ID do item

        Returns:
            Link para a página de detalhes
        """
        return f"/cautelas/item/{item_id}/"

    @staticmethod
    def criar_notificacao_cautela(policial, cautela, tipo, mensagem_extra=""):
        """
        Cria uma notificação relacionada a uma cautela.

        Args:
            policial: Objeto User (policial)
            cautela: Objeto CautelaIndividual
            tipo: TipoNotificacao
            mensagem_extra: Texto adicional para a mensagem

        Returns:
            Objeto Notificacao criado
        """
        # Certifique-se que o protocolo está definido
        protocolo = cautela.protocolo_aceite or f"CAUT-{cautela.id}-{timezone.now().strftime('%Y%m%d%H%M')}"

        # Se o protocolo não estava definido, atualize a cautela
        if not cautela.protocolo_aceite:
            cautela.protocolo_aceite = protocolo
            cautela.save(update_fields=['protocolo_aceite'])

        mensagens = {
            TipoNotificacao.CAUTELA_PENDENTE: _(
                f"Você possui uma nova cautela pendente de aceite (Protocolo: {protocolo})."
            ),
            TipoNotificacao.ACEITE_CONFIRMADO: _(
                f"Seu aceite de cautela (Protocolo: {protocolo}) foi confirmado com sucesso."
            ),
            TipoNotificacao.DEVOLUCAO_PENDENTE: _(
                f"Você precisa devolver os equipamentos da sua cautela (Protocolo: {protocolo})."
            ),
            TipoNotificacao.DEVOLUCAO_CONFIRMADA: _(
                f"Sua devolução de cautela (Protocolo: {protocolo}) foi confirmada."
            ),
        }

        titulos = {
            TipoNotificacao.CAUTELA_PENDENTE: _("Nova cautela registrada"),
            TipoNotificacao.ACEITE_CONFIRMADO: _("Aceite de cautela confirmado"),
            TipoNotificacao.DEVOLUCAO_PENDENTE: _("Devolução de cautela pendente"),
            TipoNotificacao.DEVOLUCAO_CONFIRMADA: _("Devolução de cautela confirmada"),
        }

        mensagem_base = mensagens.get(tipo, "")
        if mensagem_extra:
            mensagem_base += f" {mensagem_extra}"

        titulo = titulos.get(tipo, "Notificação de Cautela")
        link = NotificacaoService.gerar_link_cautela(cautela.id)

        return NotificacaoService.criar_notificacao(
            usuario=policial,
            titulo=titulo,
            mensagem=mensagem_base,
            tipo=tipo,
            link=link
        )

    @staticmethod
    def criar_notificacao_aceite_cautela(aceite):
        """
        Cria notificação relacionada a um aceite de cautela específico.

        Args:
            aceite: Objeto AceiteCautela

        Returns:
            Objeto Notificacao criado ou None se não for necessário notificar
        """
        try:
            cautela = aceite.cautela
            policial = cautela.policial

            # Link para a cautela
            link = NotificacaoService.gerar_link_cautela(cautela.id)

            if aceite.status == StatusAceite.CONFIRMADO:
                # Buscar notificação pendente existente
                notificacao_pendente = Notificacao.objects.filter(
                    usuario=policial,
                    tipo=TipoNotificacao.CAUTELA_PENDENTE,
                    link__contains=str(cautela.id),
                    lida=False
                ).first()

                # Atualizar status da notificação pendente
                if notificacao_pendente:
                    # Marcar a notificação pendente como lida
                    notificacao_pendente.marcar_como_lida()

                # Removemos a criação da notificação de aceite confirmado
                return None

        except Exception as e:
            # Log do erro - em ambiente de produção, use logger ao invés de print
            print(f"Erro ao criar notificação de aceite: {str(e)}")
            return None

    @staticmethod
    def criar_notificacao_item_danificado(item, mensagem_extra=""):
        """
        Cria notificações sobre um item danificado para o policial e gestor.

        Args:
            item: Objeto ItemCautela
            mensagem_extra: Texto adicional para a mensagem

        Returns:
            Lista de notificações criadas
        """
        if not item or not item.cautela:
            return []

        cautela = item.cautela
        policial = cautela.policial
        notificacoes = []

        # Verificar se o status do item justifica notificação
        if item.status_equipamento not in [StatusEquipamento.DANIFICADO, StatusEquipamento.INOPERANTE, StatusEquipamento.EXTRAVIADO]:
            return notificacoes

        # Notificação para o policial
        mensagem = _(f"O equipamento {item.get_tipo_equipamento_display()} foi registrado com danos: {item.descricao_danos}")
        if mensagem_extra:
            mensagem += f" {mensagem_extra}"

        link = NotificacaoService.gerar_link_item(item.id)

        notif_policial = NotificacaoService.criar_notificacao(
            usuario=policial,
            titulo=_("Equipamento devolvido com danos"),
            mensagem=mensagem,
            tipo=TipoNotificacao.EQUIPAMENTO_DANIFICADO,
            link=link
        )

        if notif_policial:
            notificacoes.append(notif_policial)

        # Notificação para o gestor/comandante da guarnição
        try:
            gestor = cautela.guarnicao.comandante
            if gestor and gestor != policial:
                notif_gestor = NotificacaoService.criar_notificacao(
                    usuario=gestor,
                    titulo=_("Equipamento devolvido com danos"),
                    mensagem=_(f"O equipamento {item.get_tipo_equipamento_display()} do policial {policial.name} foi registrado com danos: {item.descricao_danos}"),
                    tipo=TipoNotificacao.EQUIPAMENTO_DANIFICADO,
                    link=link
                )

                if notif_gestor:
                    notificacoes.append(notif_gestor)
        except Exception as e:
            # Em ambiente de produção, use logger ao invés de print
            print(f"Erro ao notificar gestor sobre item danificado: {str(e)}")
            pass

        return notificacoes


    @staticmethod
    def criar_notificacao_devolucao_item(item):
        """
        Cria uma notificação para a devolução de um item e já marca como lida.

        Args:
            item: Objeto ItemCautela

        Returns:
            Objeto Notificacao criado
        """
        if not item or not item.cautela or not item.cautela.policial:
            return None

        link = NotificacaoService.gerar_link_cautela(item.cautela.id)

        notificacao = NotificacaoService.criar_notificacao(
            usuario=item.cautela.policial,
            titulo=_("Equipamento devolvido"),
            mensagem=_(
                f"O equipamento {item.get_tipo_equipamento_display()} foi registrado como devolvido."
            ),
            tipo=TipoNotificacao.DEVOLUCAO_CONFIRMADA,
            link=link
        )

        # Marcar como lida automaticamente
        if notificacao:
            notificacao.lida = True
            notificacao.data_leitura = item.data_devolucao or timezone.now()
            notificacao.save(update_fields=['lida', 'data_leitura'])

        return notificacao

    @staticmethod
    def criar_notificacao_cautela_completa_devolvida(cautela):
        """
        Cria notificação informando que todos os itens da cautela foram devolvidos.
        Esta função não deve ser chamada diretamente, pois a notificação será criada
        pelo NotificationHub através do evento 'cautela_devolvida'.

        Args:
            cautela: Objeto CautelaIndividual

        Returns:
            None
        """
        # Deixar o método vazio ou adicionar um comentário explicando que
        # a notificação é gerenciada pelo NotificationHub
        return None


    @staticmethod
    def criar_notificacao_nova_cautela(cautela):
        """
        Cria notificação de nova cautela pendente de aceite.

        Args:
            cautela: Objeto CautelaIndividual

        Returns:
            Objeto Notificacao criado
        """
        if not cautela or not cautela.policial:
            return None

        # Certifique-se que o protocolo está definido
        protocolo = cautela.protocolo_aceite or f"CAUT-{cautela.id}-{timezone.now().strftime('%Y%m%d%H%M')}"

        # Se o protocolo não estava definido, atualize a cautela
        if not cautela.protocolo_aceite:
            cautela.protocolo_aceite = protocolo
            cautela.save(update_fields=['protocolo_aceite'])

        # Crie a mensagem com o protocolo já definido
        mensagem = _(f"Você possui uma nova cautela pendente de aceite (Protocolo: {protocolo}).")

        # Link para a cautela
        link = NotificacaoService.gerar_link_cautela(cautela.id)

        return NotificacaoService.criar_notificacao(
            usuario=cautela.policial,
            titulo=_("Nova cautela registrada"),
            mensagem=mensagem,
            tipo=TipoNotificacao.CAUTELA_PENDENTE,
            link=link
        )

    @staticmethod
    def obter_notificacoes_nao_lidas(usuario):
        """
        Retorna todas as notificações não lidas de um usuário.

        Args:
            usuario: Objeto User

        Returns:
            QuerySet com notificações não lidas
        """
        if not usuario:
            return Notificacao.objects.none()

        return Notificacao.objects.filter(
            usuario=usuario,
            lida=False
        ).order_by('-created_at')

    @staticmethod
    def marcar_como_lida(notificacao_id, usuario=None):
        """
        Marca uma notificação como lida.

        Args:
            notificacao_id: ID da notificação
            usuario: Objeto User (opcional para verificação de permissão)

        Returns:
            Booleano indicando sucesso
        """
        try:
            notificacao = Notificacao.objects.get(id=notificacao_id)

            # Verificar se o usuário tem permissão (se fornecido)
            if usuario and notificacao.usuario != usuario:
                return False

            notificacao.marcar_como_lida()
            return True
        except Notificacao.DoesNotExist:
            return False
