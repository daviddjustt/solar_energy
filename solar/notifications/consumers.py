import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # O usuário já está autenticado pelo AuthMiddlewareStack no asgi.py
        user = self.scope['user']
        
        if user.is_authenticated:
            # 1. Sempre adiciona o usuário ao seu grupo pessoal (para mensagens diretas)
            await self.channel_layer.group_add(
                f'user_{user.id}', 
                self.channel_name
            )

            # 2. Adiciona automaticamente aos grupos baseados nos Groups do Django
            # Isso usa a lógica que você já tem no _update_groups!
            user_groups = await database_sync_to_async(list)(user.groups.values_list('name', flat=True))
            
            for group_name in user_groups:
                await self.channel_layer.group_add(
                    group_name,  # Ex: 'Administradores', 'Tecnicos', 'Clientes'
                    self.channel_name
                )
            
            await self.accept()
        else:
            await self.close()

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