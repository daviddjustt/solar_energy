from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class OperConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arcanosig.oper'
    verbose_name = 'Operações'

    def ready(self):
        # importa o módulo de sinais para registrar handlers
        try:
            from . import signals  # noqa: F401
        except ImportError as e:
            logger.error(f"Erro ao importar sinais de arcanosig.oper: {e}")
