import json
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

User = get_user_model()

@database_sync_to_async
def get_user_from_token(token_string):
    """Abre o Token JWT e busca o usuário no banco de dados."""
    try:
        access_token = AccessToken(token_string)
        # Atenção: Dependendo de como seu JWT foi configurado, access_token['user_id'] 
        # pode ser o 'id' numérico ou o 'uuid'.
        user_identifier = access_token['user_id']
        
        # Como no seu exemplo você usou cliente.id, estamos buscando pelo ID padrão (ou UUID)
        return User.objects.get(id=user_identifier) 
    except (TokenError, InvalidToken, User.DoesNotExist):
        return None

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 1. Pega os parâmetros da URL para encontrar o ?token=...
        query_string = self.scope['query_string'].decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]

        if not token:
            print("❌ Conexão negada: Nenhum token fornecido.")
            await self.close(code=4000)
            return

        # 2. Vai no banco e descobre quem é o dono desse token
        user = await get_user_from_token(token)

        if user and user.is_authenticated:
            self.user = user
            
            # 3. 🔒 MÁGICA DA PRIVACIDADE: 
            # O nome da sala FICA EXATAMENTE IGUAL ao disparado no envio do backend
            # Ex: "user_notifications_15"
            self.room_group_name = f'user_notifications_{self.user.id}'

            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            await self.accept()
            print(f"✅ Usuário {self.user.email} (ID: {self.user.id}) TRANCADO na sala: {self.room_group_name}")
        else:
            print("❌ Conexão negada: Token inválido ou expirado.")
            await self.close(code=4001)

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # 4. Recebe o dicionário 'data' do backend (que configuramos no passo anterior)
    async def send_notification(self, event):
        data = event['data']
        
        # 5. Envia pelo túnel blindado para o frontend do usuário
        await self.send(text_data=json.dumps({
            'title': data.get('title', ''),
            'message': data.get('message', ''),
            'url': data.get('url', '')
        }))