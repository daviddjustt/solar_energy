from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

class Command(BaseCommand):
      help = 'Cria ou atualiza a tarefa periódica para enviar dados ao Google Sheets a cada 5 minutos'

      def handle(self, *args, **kwargs):
          schedule, created = IntervalSchedule.objects.get_or_create(
              every=5,
              period=IntervalSchedule.MINUTES,
          )

          PeriodicTask.objects.update_or_create(
              name='Enviar dados para o Google Sheets a cada 5 minutos',
              defaults={
                  'interval': schedule,
                  'task': 'documents.tasks.enviar_dados_para_google_sheets',
                  'args': json.dumps([]),
                  'enabled': True,
              }
          )

          self.stdout.write(self.style.SUCCESS('Tarefa periódica configurada com sucesso.'))
