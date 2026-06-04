import os
import configurations

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.config.production')
os.environ.setdefault('DJANGO_CONFIGURATION', 'Production')
configurations.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from solar.notifications.middleware import JWTAuthMiddleware
from solar.notifications.consumers import NotificationConsumer

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter([
            # Nota: usamos <str:user_id> para evitar problemas iniciais com o tipo UUID
            path("ws/notifications/<str:user_id>/", NotificationConsumer.as_asgi()),
        ])
    ),
})