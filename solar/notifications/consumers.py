import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Todo mundo que conectar entra na mesma sala pública
        self.room_group_name = 'sala_de_teste'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        print("✅ [WebSocket] Cliente conectado na sala de teste!")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Função que recebe a mensagem do Redis e manda pro Navegador
    async def send_notification(self, event):
        message = event['message']
        
        await self.send(text_data=json.dumps({
            'message': message
        }))