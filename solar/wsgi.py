"""
WSGI config for solar project.
It exposes the WSGI callable as a module-level variable named ``application``.
For more information on this file, see
https://docs.djangoproject.com/en/2.0/howto/deployment/wsgi/gunicorn/
"""
import os
from configurations import importer # Adicione esta linha
from configurations.wsgi import get_wsgi_application # Mantenha esta importação de configurations.wsgi

# CRUCIAL: Chame importer.install() antes de definir as variáveis de ambiente
# para que o django-configurations possa interceptar a importação das configurações.
importer.install()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "solar.config")
os.environ.setdefault("DJANGO_CONFIGURATION", "Production")


application = get_wsgi_application()
