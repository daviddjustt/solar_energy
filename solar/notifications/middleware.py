import urllib.parse
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()

@database_sync_to_async
def get_user(user_uuid):
    try:
        # Busca o usuário pelo UUID, já que seu settings.py define USER_ID_FIELD = 'uuid'
        return User.objects.get(uuid=user_uuid)
    except User.DoesNotExist:
        return AnonymousUser()

class JWTAuthMiddleware:
    """
    Middleware customizado que extrai o token da query string: wss://...?token=ey...
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # 1. Captura a URL e extrai os parâmetros
        query_string = scope.get("query_string", b"").decode()
        query_params = urllib.parse.parse_qs(query_string)
        token = query_params.get("token", [None])[0]

        # 2. Valida o Token
        if token:
            try:
                access_token = AccessToken(token)
                user_id = access_token['user_id']
                # 3. Injeta o usuário autenticado no escopo
                scope['user'] = await get_user(user_id)
            except Exception:
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()

        return await self.app(scope, receive, send)