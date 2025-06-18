from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from arcanosig.oper.models.notificacao import Notificacao
from arcanosig.oper.models.enums import TipoNotificacao


class NotificationHub:
    """
    Hub central para gerenciar eventos e notificações no sistema.
    Implementa o padrão Observer para reagir a eventos do sistema.
    """

    @staticmethod
    def gerar_link(tipo, objeto_id):
        """
        Gera links padronizados para cada tipo de objeto.

        Args:
            tipo: Tipo de objeto (cautela, item, etc)
            objeto_id: ID do objeto

        Returns:
            String com o link gerado
        """
        links = {
            'cautela': f"/cautelas/detalhe/{objeto_id}/",
            'item': f"/cautelas/item/{objeto_id}/",
            'aceite': f"/cautelas/aceite/{objeto_id}/",
        }
        return links.get(tipo, "/")

    @staticmethod
    def criar_notificacao(usuario, titulo, mensagem, tipo, link=""):
        """
        Método centralizado para criar notificações.

        Args:
            usuario: Usuário destinatário
            titulo: Título da notificação
            mensagem: Corpo da mensagem
            tipo: Tipo da notificação (enum)
            link: Link opcional para ação

        Returns:
            Objeto Notificacao criado ou None
        """
        if not usuario:
            return None

        try:
            return Notificacao.objects.create(
                usuario=usuario,
                titulo=titulo,
                mensagem=mensagem,
                tipo=tipo,
                link=link
            )
        except Exception as e:
            # Em produção, usar logger ao invés de print
            print(f"Erro ao criar notificação: {str(e)}")
            return None

    @staticmethod
    def marcar_notificacoes_relacionadas_como_lidas(usuario, tipo=None, link_contains=None):
        """
        Marca notificações relacionadas como lidas.

        Args:
            usuario: Usuário
            tipo: Tipo específico de notificação
            link_contains: Texto contido no link

        Returns:
            Número de notificações atualizadas
        """
        queryset = Notificacao.objects.filter(usuario=usuario, lida=False)

        if tipo:
            queryset = queryset.filter(tipo=tipo)

        if link_contains:
            queryset = queryset.filter(link__contains=link_contains)

        count = queryset.count()
        queryset.update(lida=True, data_leitura=timezone.now())
        return count

    @staticmethod
    def emit_event(event_name, **kwargs):
        """
        Emite um evento para o sistema de notificações.

        Args:
            event_name: Nome do evento
            **kwargs: Parâmetros adicionais do evento

        Returns:
            None
        """
        # Mapear eventos para handlers
        handlers = {
            'cautela_criada': NotificationHub._handle_cautela_criada,
            'aceite_processado': NotificationHub._handle_aceite_processado,
            'item_devolvido': NotificationHub._handle_item_devolvido,
            'cautela_devolvida': NotificationHub._handle_cautela_devolvida,
        }

        # Chamar o handler apropriado
        handler = handlers.get(event_name)
        if handler:
            handler(**kwargs)

    @staticmethod
    def _handle_cautela_criada(cautela, aceite=None, **kwargs):
        """Handler para evento de cautela criada"""
        # Notificar o policial sobre a nova cautela
        policial = cautela.policial
        link = NotificationHub.gerar_link('cautela', cautela.id)

        NotificationHub.criar_notificacao(
            usuario=policial,
            titulo=_("Nova cautela pendente"),
            mensagem=_(f"Você possui uma nova cautela pendente de aceite (Protocolo: {cautela.protocolo_aceite})."),
            tipo=TipoNotificacao.CAUTELA_PENDENTE,
            link=link
        )

    @staticmethod
    def _handle_aceite_processado(aceite, cautela, usuario_acao=None, **kwargs):
        """Handler para evento de aceite processado (confirmado)"""
        policial = cautela.policial
        link = NotificationHub.gerar_link('cautela', cautela.id)

        # Marcar antigas notificações pendentes como lidas
        notificacoes_pendentes = Notificacao.objects.filter(
            usuario=policial,
            tipo=TipoNotificacao.CAUTELA_PENDENTE,
            link__contains=str(cautela.id),
            lida=False
        )

        # Atualizar com a data do aceite
        notificacoes_pendentes.update(
            lida=True,
            data_leitura=aceite.data_aceite or timezone.now()
        )


    @staticmethod
    def _handle_item_devolvido(item, cautela, com_danos=False, usuario_acao=None, **kwargs):
        """Handler para evento de item devolvido"""
        policial = cautela.policial
        link = NotificationHub.gerar_link('item', item.id)

        # Notificar sobre a devolução do item E já marcar como lida
        notificacao = NotificationHub.criar_notificacao(
            usuario=policial,
            titulo=_("Item devolvido"),
            mensagem=_(f"O item {item.get_tipo_equipamento_display()} foi registrado como devolvido."),
            tipo=TipoNotificacao.DEVOLUCAO_CONFIRMADA,
            link=link
        )

        # Marcar a notificação de devolução como lida automaticamente
        if notificacao:
            notificacao.lida = True
            notificacao.data_leitura = item.data_devolucao or timezone.now()
            notificacao.save(update_fields=['lida', 'data_leitura'])

        # Se o item foi devolvido com danos, criar notificação adicional
        if com_danos:
            # Notificar o policial
            notificacao_danos = NotificationHub.criar_notificacao(
                usuario=policial,
                titulo=_("Equipamento com danos"),
                mensagem=_(f"O equipamento {item.get_tipo_equipamento_display()} foi registrado com danos/problemas."),
                tipo=TipoNotificacao.EQUIPAMENTO_DANIFICADO,
                link=link
            )

            # Se o policial for o mesmo que relatou os danos, marcar como lida
            if notificacao_danos and usuario_acao and usuario_acao == policial:
                notificacao_danos.marcar_como_lida()


    @staticmethod
    def _handle_cautela_devolvida(cautela, usuario_acao=None, **kwargs):
        """Handler para evento de cautela completamente devolvida"""
        policial = cautela.policial
        link = NotificationHub.gerar_link('cautela', cautela.id)

        # Notificar sobre devolução completa E já marcar como lida
        notificacao = NotificationHub.criar_notificacao(
            usuario=policial,
            titulo=_("Cautela devolvida"),
            mensagem=_(f"Todos os itens da cautela (Protocolo: {cautela.protocolo_aceite}) foram devolvidos."),
            tipo=TipoNotificacao.DEVOLUCAO_CONFIRMADA,
            link=link
        )

        # Marcar a notificação de devolução completa como lida automaticamente
        if notificacao:
            notificacao.lida = True
            notificacao.data_leitura = cautela.data_devolucao or timezone.now()
            notificacao.save(update_fields=['lida', 'data_leitura'])
