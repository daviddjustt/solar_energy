import os
import configurations
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.config.production') # Certifique-se que aponta para a config correta
os.environ.setdefault('DJANGO_CONFIGURATION', 'Production')
configurations.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from solar.notifications.middleware import JWTAuthMiddleware # Nosso novo arquivo
from solar.notifications.consumers import NotificationConsumer

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware( # <--- AQUI ESTÁ O SEGREDO
        URLRouter([
            path("ws/notifications/<uuid:user_id>/", NotificationConsumer.as_asgi()),
        ])
    ),
})