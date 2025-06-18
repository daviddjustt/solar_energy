from rest_framework import serializers
from arcanosig.users.models import User


class BaseModelSerializer(serializers.ModelSerializer):
    """
    Serializer base para todos os modelos do sistema.
    Fornece campos comuns de auditoria.
    """
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer simplificado para o modelo User quando usado em outros serializers.
    """
    display_name = serializers.SerializerMethodField()
    patent_display = serializers.CharField(source='get_patent_display', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'patent', 'patent_display', 'display_name', 'photo']
        read_only_fields = fields

    def get_display_name(self, obj):
        """Retorna nome formatado para exibição"""
        if obj.patent != 'NAO_APLICAVEL':
            return f"{obj.get_patent_display()} {obj.name}"
        return obj.name
