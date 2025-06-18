from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from arcanosig.oper.models.base import BaseModel
from arcanosig.oper.models.enums import TipoNotificacao
from arcanosig.users.models import User


class Notificacao(BaseModel):
    """
    Modelo para registrar notificações enviadas aos usuários.
    """
    usuario = models.ForeignKey(
        User,
        verbose_name=_("Usuário"),
        on_delete=models.CASCADE,
        related_name="notificacoes",
    )
    titulo = models.CharField(
        verbose_name=_("Título"),
        max_length=100,
    )
    mensagem = models.TextField(
        verbose_name=_("Mensagem"),
    )
    tipo = models.CharField(
        verbose_name=_("Tipo"),
        max_length=30,
        choices=TipoNotificacao.choices,
        db_index=True,  # Adicionando índice para melhorar queries por tipo
    )
    lida = models.BooleanField(
        verbose_name=_("Lida"),
        default=False,
        db_index=True,  # Adicionando índice para melhorar queries de não lidas
    )
    data_leitura = models.DateTimeField(
        verbose_name=_("Data de Leitura"),
        null=True,
        blank=True,
    )
    link = models.CharField(
        verbose_name=_("Link"),
        max_length=255,
        blank=True,
    )
    # Campo para referências de objeto
    objeto_id = models.UUIDField(
        verbose_name=_("ID do objeto referenciado"),
        null=True,
        blank=True,
        help_text=_("ID do objeto ao qual a notificação se refere (cautela, item, etc)")
    )
    objeto_tipo = models.CharField(
        verbose_name=_("Tipo do objeto referenciado"),
        max_length=30,
        blank=True,
        help_text=_("Tipo do objeto referenciado (cautela, item, etc)")
    )

    class Meta:
        verbose_name = _("Notificação")
        verbose_name_plural = _("Notificações")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['usuario', 'lida']),  # Índice composto para consultas frequentes
            models.Index(fields=['tipo', 'usuario']),  # Índice composto para filtros por tipo
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} - {self.usuario.name} ({self.created_at.strftime('%d/%m/%Y')})"

    def marcar_como_lida(self):
        """Marca a notificação como lida"""
        if not self.lida:
            self.lida = True
            self.data_leitura = timezone.now()
            self.save(update_fields=['lida', 'data_leitura'])
            return True
        return False
