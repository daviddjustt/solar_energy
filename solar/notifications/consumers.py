import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        # 1. Barreira de Segurança: Se o token for inválido, derruba a conexão (403)
        if not self.user.is_authenticated:
            await self.close()
            return

        # 2. Cria a sala pessoal do usuário (Exatamente como está no seu services.py)
        self.personal_group = f"user_notifications_{self.user.id}"

        # 3. Inscreve o usuário na sua sala pessoal
        await self.channel_layer.group_add(
            self.personal_group,
            self.channel_name
        )

        # 4. Se o usuário for Admin, inscreve ele também na sala "Administradores"
        if getattr(self.user, 'is_admin', False) or getattr(self.user, 'is_superuser', False):
            await self.channel_layer.group_add(
                "Administradores",
                self.channel_name
            )

        # 5. Aceita o aperto de mão
        await self.accept()
        print(f"✅ Conectado: {self.user.email} | Grupo: {self.personal_group}")

    async def disconnect(self, close_code):
        # Remove o usuário das salas quando ele fecha a aba do navegador
        if hasattr(self, 'personal_group'):
            await self.channel_layer.group_discard(
                self.personal_group,
                self.channel_name
            )
        
        if getattr(self.user, 'is_admin', False) or getattr(self.user, 'is_superuser', False):
            await self.channel_layer.group_discard(
                "Administradores",
                self.channel_name
            )

    # 6. O RECEBEDOR: Esta função é chamada automaticamente pelo services.py
    async def send_notification(self, event):
        data = event['data']
        
        # Envia os dados finais para o Front-end em formato JSON
        await self.send(text_data=json.dumps({
            'type': 'new_notification',
            'payload': data
        }))
        
