from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    # Campos complementares para o Front-end exibir informações sem precisar de outro GET
    sender_name = serializers.CharField(source='sender.name', read_only=True, default='Sistema')
    project_code = serializers.CharField(source='project.codigoCliente', read_only=True)
    project_title = serializers.CharField(source='project.nomeTitular', read_only=True)
    
    # --- RESOLUÇÃO DO P2-16: Campos do Módulo de Serviços ---
    service_id = serializers.PrimaryKeyRelatedField(source='service', read_only=True)
    service_tipo = serializers.CharField(source='service.tipo.nome', read_only=True, default=None)
    # --------------------------------------------------------
    
    # Formatação amigável de datas
    created_at_formatted = serializers.DateTimeField(
        source='created_at', format='%d/%m/%Y %H:%M', read_only=True
    )
    read_at_formatted = serializers.DateTimeField(
        source='read_at', format='%d/%m/%Y %H:%M', read_only=True
    )

    class Meta:
        model = Notification
        # Listamos os campos essenciais. Note que 'recipient' e 'is_read' são controlados pelo backend,
        # mas expostos aqui para leitura do Front-end.
        fields = [
            'id',
            'project',
            'project_code',
            'project_title',
            'service_id',      # Injetado
            'service_tipo',    # Injetado
            'sender',
            'sender_name',
            'recipient',
            'title',
            'message',
            'category',
            'is_read',
            'created_at',
            'created_at_formatted',
            'read_at',
            'read_at_formatted',
        ]
        # Garantimos que, por padrão, o Front-end não consiga alterar nenhum desses dados via PUT/PATCH diretos
        read_only_fields = [
            'id', 'project', 'sender', 'recipient', 'title', 
            'message', 'category', 'is_read', 'read_at',
            'service_id', 'service_tipo' # Injetados
        ]