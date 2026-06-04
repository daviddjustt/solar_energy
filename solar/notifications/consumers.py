import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Temporariamente, vamos aceitar QUALQUER conexão
        await self.accept()
        print("✅ Conexão WebSocket aceita com sucesso (Modo Teste)!")

    async def disconnect(self, close_code):
        print(f"❌ Conexão encerrada.")