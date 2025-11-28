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
        read_only_fields = ['approved_at']

    def validate_document_type(self, value):
        """
        Validação básica do tipo de documento.
        """
        valid_types = [choice[0] for choice in DOCUMENT_TYPE_CHOICES]

        if value not in valid_types:
            raise serializers.ValidationError(
                f"Tipo de documento inválido. Escolha entre: {', '.join(valid_types)}"
            )

        return value

    def validate_related_payment_document(self, value):
        """
        Converte valores inválidos (0, "0", "") para None.
        """
        if value in [0, '0', '']:
            return None

        return value

    def validate(self, data):
        """
        ✅ VALIDAÇÃO DE NÍVEL DE OBJETO - Executa DEPOIS de todas as validações de campo.
        Garante que comprovantes de pagamento tenham boleto relacionado.
        """
        document_type = data.get('document_type')
        related_payment_document = data.get('related_payment_document')

        # ✅ Se for comprovante de pagamento, DEVE ter boleto relacionado
        if document_type == "comprovante_de_pagamento":
            # Durante update, pode não ter document_type em data, usa o da instância
            if self.instance:
                document_type = document_type or self.instance.document_type
                related_payment_document = related_payment_document or self.instance.related_payment_document

            # ✅ Validação estrita: DEVE ter um ID válido
            if not related_payment_document:
                raise serializers.ValidationError({
                    'related_payment_document': 
                        'Comprovante de pagamento deve ter um boleto relacionado. '
                        'Informe o ID do documento de pagamento.'
                })

        return data

    def create(self, validated_data):
        """
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