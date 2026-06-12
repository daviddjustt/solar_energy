import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 1. Colocamos quem conectar na sala que a sua View dispara
        self.room_group_name = 'Administradores'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        print(f"✅ [WebSocket] Cliente sintonizado na sala: {self.room_group_name}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # 2. O nome dessa função bate com o "type": "send_notification" da sua view
    async def send_notification(self, event):
        # 3. Pega o dicionário 'data' que você enviou no processar_solicitacao_vistoria
        data = event['data']
        
        # 4. Envia pro Frontend exatamente com a estrutura que ele precisa
        await self.send(text_data=json.dumps({
            'title': data['title'],
            'message': data['message'],
            'url': data.get('url', '') # Usa .get() para evitar erro caso não tenha URL
        }))