import os
import configurations
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.config.production') # Use o seu config correto
os.environ.setdefault('DJANGO_CONFIGURATION', 'Production')
configurations.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from solar.notifications.consumers import NotificationConsumer

# Removemos o AuthMiddlewareStack para testar se é ele que derruba a conexão
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter([
        path("ws/notifications/", NotificationConsumer.as_asgi()),
    ]),
})