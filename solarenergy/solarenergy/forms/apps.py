from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class SolarenergyFormsConfig(AppConfig):
    # Use um label único para o seu app local
    label = 'solarenergy_forms'
    name = 'solarenergy.forms'
    verbose_name = _("Solarenergy Forms")
    
    def ready(self):
            # Importe sinais ou outras configurações aqui, se necessário
            pass
