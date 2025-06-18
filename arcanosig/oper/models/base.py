from django.db import models
from django.utils.translation import gettext_lazy as _


class BaseModel(models.Model):
    """
    Modelo base que fornece campos de auditoria para todos os modelos do sistema.
    Todos os modelos devem herdar desta classe para ter consistência na
    rastreabilidade de criação e atualização.
    """
    created_at = models.DateTimeField(
        verbose_name=_("Data de Criação"),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        verbose_name=_("Data de Atualização"),
        auto_now=True
    )

    class Meta:
        abstract = True
