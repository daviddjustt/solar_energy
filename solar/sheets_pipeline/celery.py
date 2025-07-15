# solar/sheets_pipeline/celery.py

import os
from celery import Celery
from configurations import importer # Adicione esta linha

# CRUCIAL: Chame importer.install() antes de definir DJANGO_SETTINGS_MODULE
importer.install()

# Define o módulo de configurações padrão do Django para o programa 'celery'.
# APONTE PARA O PACOTE QUE CONTÉM SUAS CLASSES DE CONFIGURAÇÃO (solar.config)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.config')

app = Celery('solar')

# Usando um objeto de configuração do Django.
# Isso significa que todas as configurações do Celery com um prefixo `CELERY_`
# serão lidas do objeto de configurações do Django.
# O 'namespace' deve ser 'CELERY' para que ele leia as variáveis CELERY_ do Django settings.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Carrega os módulos de tarefas de todos os aplicativos Django registrados.
app.autodiscover_tasks()

# Opcional: Tarefa de depuração para verificar se o Celery está funcionando.
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
