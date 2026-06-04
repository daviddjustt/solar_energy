import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        
        if user.is_authenticated:
            # Definimos o grupo pessoal para uso no disconnect
            self.group_names = [f'user_{user.id}']
            
            # 1. Adiciona ao grupo pessoal
            await self.channel_layer.group_add(self.group_names[0], self.channel_name)

            # 2. Adiciona aos grupos do Django
            user_groups = await database_sync_to_async(list)(user.groups.values_list('name', flat=True))
            for group_name in user_groups:
                self.group_names.append(group_name)
                await self.channel_layer.group_add(group_name, self.channel_name)
            
            await self.accept()
            print(f"✅ Usuário {user.username} conectado aos grupos: {self.group_names}")
        else:
            await self.close()

    async def disconnect(self, close_code):
        # Remove a conexão de todos os grupos em que foi adicionado
        if hasattr(self, 'group_names'):
            for group_name in self.group_names:
                await self.channel_layer.group_discard(group_name, self.channel_name)
        print(f"❌ Conexão encerrada.")

    async def send_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'title': event['data']['title'],
            'message': event['data']['message'],
            'url': event['data'].get('url', '#')
        }))