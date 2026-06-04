import os
import configurations

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.config.local')
os.environ.setdefault('DJANGO_CONFIGURATION', 'Local')
configurations.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path

# IMPORTAMOS O NOSSO NOVO MIDDLEWARE
from solar.notifications.middleware import JWTAuthMiddleware
from solar.notifications.consumers import NotificationConsumer

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware( # <--- A MÁGICA ACONTECE AQUI
        URLRouter([
            path("ws/notifications/<uuid:user_id>/", NotificationConsumer.as_asgi()),
        ])
    ),
})