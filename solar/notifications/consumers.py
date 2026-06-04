import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # O user_id vem da URL configurada no asgi.py
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.group_name = f'user_notifications_{self.user_id}'

        # Adiciona o canal ao grupo específico do usuário no Redis
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        print(f"✅ Conexão WebSocket estabelecida para usuário: {self.user_id}")

    async def disconnect(self, close_code):
        # Remove a conexão do grupo ao fechar a aba
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        print(f"❌ Conexão WebSocket encerrada para usuário: {self.user_id}")

    # Este método é chamado quando disparamos uma notificação via send_notification
    async def send_notification(self, event):
        # Envia o JSON para o frontend
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'title': event['data']['title'],
            'message': event['data']['message'],
            'url': event['data'].get('url', '#')
        }))