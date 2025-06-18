
from django.apps import AppConfig


class OperConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arcanosig.sac'
    verbose_name = 'Sac'

    def ready(self):
        import arcanosig.sac.signals
