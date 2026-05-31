# solar/notifications/views.py
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import time
from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from .models import Notification
from .serializers import NotificationSerializer  # Crie um ModelSerializer padrão para o modelo


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para listar e gerenciar notificações de forma segura.
    Removido mixins de Create/Update diretos para evitar mutações maliciosas.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        # O usuário só pode listar as notificações que ELE recebeu
        return Notification.objects.filter(recipient=self.request.user)

    def event_stream(user_id):
        """
        Gerador assíncrono conceitual. À posteriori, podemos integrar com Redis, 
        Postgres LISTEN/NOTIFY ou simplesmente checar o banco.
        """
        last_checked = timezone.now()
        while True:
            # Busca notificações novas criadas após o último ciclo
            new_notifications = Notification.objects.filter(
                recipient_id=user_id, 
                is_read=False, 
                created_at__gt=last_checked
            )
            
            if new_notifications.exists():
                for notif in new_notifications:
                    yield f"data: {{'id': {notif.id}, 'title': '{notif.title}', 'project_id': {notif.project_id}}}\n\n"
                last_checked = timezone.now()
                
            time.sleep(3) # Aguarda 3 segundos para a próxima checagem ativa (Streaming Polling)

    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    def stream_notifications(request):
        """
        Endpoint que o Front-end vai abrir usando `new EventSource('/api/v1/notifications/stream/')`
        """
        response = StreamingHttpResponse(event_stream(request.user.id), content_type="text/event-stream")
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no' # Crucial se você usar Nginx como Proxy reverso
        return response
        
    @action(detail=True, methods=['post'], url_path='mark-as-read')
    def mark_as_read(self, request, pk=None):
        """
        Garante que APENAS o recebedor pode alterar o status para lido.
        """
        try:
            # Forçamos a busca garantindo que o recipient é o usuário logado
            notification = Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist:
            return Response(
                {"detail": "Notificação não encontrada ou acesso negado."},
                status=status.HTTP_404_NOT_FOUND
            )

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=['is_read', 'read_at'])
            
            # Espaço para injetar regras de negócio à posteriori através de hooks/signals
            # ex: dispatch_notification_read_event(notification)

        return Response({"status": "Notificação marcada como lida."}, status=status.HTTP_200_OK)