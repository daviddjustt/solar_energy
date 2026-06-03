import os
from django.core.asgi import get_asgi_application

# Substitua 'solar.settings' pelo caminho correto se o seu projeto tiver outro nome
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.settings')

# 1. Inicializa a aplicação HTTP do Django primeiro (obrigatório para carregar as apps)
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from solar.notifications.consumers import NotificationConsumer # Vamos criar isto no Passo 3!

# 2. Roteador Principal
application = ProtocolTypeRouter({
    # Tráfego HTTP normal (A sua API REST continua a funcionar perfeitamente)
    "http": django_asgi_app,

    # Tráfego WebSocket (Para as notificações em tempo real)
    "websocket": AuthMiddlewareStack(
        URLRouter([
            # A rota que o Front-end vai usar para se conectar ao canal do utilizador
            path("ws/notifications/<int:user_id>/", NotificationConsumer.as_asgi()),
        ])
    ),
})
