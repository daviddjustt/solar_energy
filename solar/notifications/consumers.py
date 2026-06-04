import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print(f"DEBUG: Tentando conectar...")
        print(f"DEBUG: Usuário no escopo: {self.scope.get('user')}")
        
        # Aceita a conexão incondicionalmente
        await self.accept()
        print("✅ Conexão WebSocket aceita!")

    async def disconnect(self, close_code):
        print(f"❌ Conexão encerrada.")