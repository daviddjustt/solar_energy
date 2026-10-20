from rest_framework import serializers
from solar.services.models import ServiceType, ServiceRequest
from solar.users.models import User  # Importe o modelo de utilizador correto
# Importe os restantes modelos à medida que forem criados (ServiceAttachment, etc.)

class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceType
        fields = '__all__'

class ExternalUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"
        # Pode querer definir read_only para certos campos do core user se necessário

class ServiceRequestSerializer(serializers.ModelSerializer):
    tipo_detalhe = ServiceTypeSerializer(source='tipo', read_only=True)

    class Meta:
        model = ServiceRequest
        # Campos que o utilizador não pode preencher/alterar manualmente:
        read_only_fields = [
            'solicitante', 
            'status', 
            'executor', 
            'valor_cobrado', 
            'payment_status',
            'motivo_reprova'
        ]
        fields = '__all__'

    def create(self, validated_data):
        # O valor do serviço é copiado para a solicitação no momento da abertura.
        # Isto garante que mudanças de preço futuras não alterem pedidos antigos.
        tipo = validated_data['tipo']
        validated_data['valor_cobrado'] = tipo.valor
        
        return super().create(validated_data)