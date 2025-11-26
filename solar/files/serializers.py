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
    # O campo 'user' será definido pela view (do URL ou contexto)
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    # Campos de auditoria e propriedades customizadas são read-only
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    approved_at = serializers.DateTimeField(read_only=True)

    # Propriedades customizadas do modelo
    days_since_upload = serializers.IntegerField(read_only=True)
    is_recent = serializers.BooleanField(read_only=True)
    is_payment_document = serializers.BooleanField(read_only=True)
    is_payment_complete = serializers.BooleanField(read_only=True)
    payment_status = serializers.CharField(read_only=True)

    class Meta:
        model = DocumentUser
        fields = '__all__'
        read_only_fields = ['status', 'approved_at', 'user']

    def create(self, validated_data):
        """
        ✅ CORRIGIDO: Removido o parâmetro 'value' que causava o erro.
        Sobrescreve o método create para usar o usuário fornecido no contexto da view.
        """
        user = self.context.get('user')

        if not user:
            raise serializers.ValidationError(
                "O usuário deve ser fornecido para a criação de DocumentUser."
            )

        validated_data['user'] = user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """
        Sobrescreve o método update para prevenir a alteração do campo 'user'.
        """
        validated_data.pop('user', None)
        return super().update(instance, validated_data)

    def validate_document_type(self, value):
        """
        ✅ VALIDAÇÃO CONSOLIDADA: Toda a lógica de validação do document_type aqui.
        """
        valid_types = [choice[0] for choice in DOCUMENT_TYPE_CHOICES]

        if value not in valid_types:
            raise serializers.ValidationError(
                f"Tipo de documento inválido. Escolha entre: {', '.join(valid_types)}"
            )

        # ✅ Validação específica para comprovante de pagamento
        if value == "comprovante_pagamento":
            related_payment_document = self.initial_data.get('related_payment_document')

            # Durante a atualização, verifica na instância existente
            if hasattr(self, 'instance') and self.instance:
                related_payment_document = related_payment_document or self.instance.related_payment_document

            # ✅ Aceita None/null mas não aceita 0 ou strings vazias
            if related_payment_document in [0, '0', '']:
                raise serializers.ValidationError(
                    "Para comprovante de pagamento, forneça um ID de boleto válido ou deixe em branco."
                )

            # Se forneceu um ID, valida se é um número válido
            if related_payment_document and not str(related_payment_document).isdigit():
                raise serializers.ValidationError(
                    "O ID do boleto relacionado deve ser um número válido."
                )

        return value

    def validate_related_payment_document(self, value):
        """
        ✅ VALIDAÇÃO DO CAMPO related_payment_document.
        Evita que valores inválidos como 0 sejam aceitos.
        """
        # Se o valor for 0, converte para None
        if value == 0:
            return None

        # Se for string "0", também converte para None
        if isinstance(value, str) and value == "0":
            return None

        return value
