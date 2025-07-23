from django.apps import AppConfig
from django_celery_beat.models import IntervalSchedule, PeriodicTask
import json

class SeuAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'documents'

    def ready(self):

          # Criar ou obter um intervalo de 5 minutos
          schedule, created = IntervalSchedule.objects.get_or_create(
              every=5,
              period=IntervalSchedule.MINUTES,
          )

          # Criar ou atualizar a tarefa periódica
          PeriodicTask.objects.update_or_create(
              name='Enviar dados para o Google Sheets a cada 5 minutos',
              defaults={
                  'interval': schedule,
                  'task': 'documents.tasks.enviar_dados_para_google_sheets',
                  'args': json.dumps([]),
                  'enabled': True,
              }
          )
