# solar/documents/serializers.py

from rest_framework import serializers
from .models import DocumentUser
from solar.files.utils import DOCUMENT_TYPE_CHOICES, STATUS_CHOICES

class DocumentUserSerializer(serializers.ModelSerializer):
    """
    Serializer para o modelo DocumentUser.
    Permite a serialização e desserialização de documentos relacionados a usuários,
    incluindo o upload de arquivos.
    """
    # O campo 'user' será definido pela view (do URL ou contexto),
    # então ele é read_only aqui para evitar que o cliente o envie diretamente.
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    # Campos de auditoria e propriedades customizadas são geralmente read-only
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    approved_at = serializers.DateTimeField(read_only=True) # Definido pela lógica do modelo

    # Propriedades customizadas do modelo DocumentUser (ou Document)
    days_since_upload = serializers.IntegerField(read_only=True)
    is_recent = serializers.BooleanField(read_only=True)
    is_payment_document = serializers.BooleanField(read_only=True)
    is_payment_complete = serializers.BooleanField(read_only=True)
    payment_status = serializers.CharField(read_only=True)

    class Meta:
        model = DocumentUser
        fields = '__all__'
        # 'status' e 'approved_at' são geralmente gerenciados pela lógica de negócio
        # e não diretamente pelo usuário na criação/atualização.
        read_only_fields = ['status', 'approved_at']

    def create(self, validated_data):
        """
        Sobrescreve o método create para usar o usuário fornecido no contexto da view.
        """
        user = self.context.get('user')
        if not user:
            # Esta validação é uma "rede de segurança" caso a view não injete o usuário
            raise serializers.ValidationError("O usuário deve ser fornecido para a criação de DocumentUser.")
        validated_data['user'] = user
        return super().create(validated_data)
        

    def update(self, instance, validated_data):
        """
        Sobrescreve o método update para prevenir a alteração do campo 'user'.
        """
        validated_data.pop('user', None) # Remove 'user' se presente para evitar alteração
        return super().update(instance, validated_data)

    # Exemplo de validação customizada para o tipo de documento, se necessário
    def validate_document_type(self, value):
        valid_types = [choice[0] for choice in DOCUMENT_TYPE_CHOICES]
        if value not in valid_types:
            raise serializers.ValidationError(f"Tipo de documento inválido. Escolha entre: {', '.join(valid_types)}")
        elif valid_types == "comprovante_pagamento" and DocumentUser.related_payment_document == None:
            raise serializers.ValidationError(f"Comprovante de pagamento precisa ter um boleto relacionado: {', '.join(valid_types)}")
        return value
