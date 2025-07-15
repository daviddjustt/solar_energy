# myproject/myproject/celery.py

import os
from solar.sheets_pipeline.celery import Celery

# Define o módulo de configurações padrão do Django para o 'celery'
# Isso garante que o Celery use as configurações do seu projeto Django.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.config.common') # Substitua 'myproject' pelo nome do seu projeto

app = Celery('solar') # Substitua 'myproject' pelo nome do seu projeto

# Usando um objeto de configuração do Django.
# O Celery irá automaticamente descobrir as configurações de tarefas em todos os
# arquivos `tasks.py` dentro dos aplicativos listados em INSTALLED_APPS.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Carrega os módulos de tarefas de todos os aplicativos Django registrados.
app.autodiscover_tasks()

# Opcional: Tarefa de depuração para verificar se o Celery está funcionando.
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

