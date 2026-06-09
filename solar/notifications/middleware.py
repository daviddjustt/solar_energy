import urllib.parse
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from django.http import parse_cookie

User = get_user_model()

@database_sync_to_async
def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except:
        return AnonymousUser()

class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # 1. Pegar todos os cookies da requisição
        headers = dict(scope.get('headers', []))
        cookies_header = headers.get(b'cookie', b'').decode()
        cookies = parse_cookie(cookies_header)
        
        # LOG para depuração (olhe o terminal do Railway!)
        print(f"DEBUG: Cookies recebidos: {cookies.keys()}")

        # 2. Tentar encontrar o token (mude 'access_token' para o nome exato do seu cookie se for diferente)
        # Se você não sabe o nome, o print acima vai te mostrar.
        token = cookies.get('access_token') or cookies.get('jwt') 

        if token:
            try:
                access_token = AccessToken(token)
                user_id = access_token['user_id']
                scope['user'] = await get_user(user_id)
            except Exception as e:
                print(f"DEBUG: Erro ao validar token: {e}")
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()

        return await self.app(scope, receive, send)