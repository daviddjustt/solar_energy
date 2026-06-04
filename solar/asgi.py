import os
import configurations  # <--- IMPORTANTE: Importar aqui

# 1. Configurar o ambiente antes de tudo
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.config.local') # Ajuste o caminho se necessário
os.environ.setdefault('DJANGO_CONFIGURATION', 'Local')               # O nome da sua classe no local.py
configurations.setup()                                               # <--- A MÁGICA: Isso inicializa o django-configurations

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from solar.notifications.consumers import NotificationConsumer

# 2. Agora o Django pode carregar as configurações corretamente
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path("ws/notifications/<uuid:user_id>/", NotificationConsumer.as_asgi()),
        ])
    ),
})