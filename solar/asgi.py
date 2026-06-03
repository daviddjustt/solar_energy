import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
# Importe o seu consumer (vamos criar no Passo 3)
#from solar.notifications.consumers import NotificationConsumer

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.settings')

# Inicializa o handler HTTP do Django
django_asgi_app = get_asgi_application()

#application = ProtocolTypeRouter({
#        "http": django_asgi_app,
#        "websocket": AuthMiddlewareStack(
#            URLRouter([
#                path("ws/notifications/<int:user_id>/", NotificationConsumer.as_asgi()),
#            ])
#        ),
#    })
