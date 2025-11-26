import logging
import re
from django.utils.html import escape
# Django CORE imports
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _

# Third-party imports
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from djoser.serializers import UserSerializer as DjoserUserSerializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError
from djoser.serializers import UserDeleteSerializer

# Local application imports
from .models import User

logger = logging.getLogger(__name__)

class UserCreateSerializer(DjoserUserCreateSerializer):
    """Serializer para criação de usuários com tratamento especial."""

    class Meta(DjoserUserCreateSerializer.Meta):
        model = User
        fields = tuple(set(DjoserUserCreateSerializer.Meta.fields + ('name', 'cnpj', 'cpf', 'celular', 'is_pessoa_juridica')))
        extra_kwargs = {
            'name': {'required': True},
            'is_pessoa_juridica': {'required': True},
            'celular': {'required': True},
            'cnpj': {'required': False}, # Max 18 para CNPJ formatado
            'cpf': {'required': False},  # Max 14 para CPF formatado
            # 'password' já é required por padrão no DjoserUserCreateSerializer, email também
        }

    def validate(self, attrs):
        """Validação global com normalização de dados. Importante !"""
        attrs = super().validate(attrs)
        # Normalização de campos
        attrs['name'] = attrs.get('name', '').strip().upper()
        attrs['celular'] = re.sub(r'\D', '', attrs.get('celular', '')) # Remove não dígitos

        # Validação de cnpj (exemplo básico, considere uma validação mais robusta)
        if ('is_pessoa_juridica' == True):
            if len(attrs['cnpj']) != 18:
                raise DRFValidationError({"cnpj": _("cnpj deve conter 18 caracteres.")})
        else :
            if len(attrs['cpf']) != 14:
                raise DRFValidationError({"cpf": _("cpf deve conter 14 caracteres.")})

        # Validação de Celular (exemplo básico)
        if len(attrs['celular']) != 11:
             raise DRFValidationError({"celular": _("Celular deve conter 11 dígitos numéricos (DDD + número).")})
        return attrs

    def create(self, validated_data):
        """Criação do usuário com tratamento seguro de campos."""
        try:
            # Usando o método create_user que já configura as permissões básicas
            # e trata a senha de forma segura.
            user = User.objects.create_user(**validated_data)
            logger.info(f"Usuário criado: {user.email}")
            return user
        except DjangoValidationError as e:
             # Captura ValidationErrors específicos do modelo/clean methods
             logger.error(f"Erro de validação Django ao criar usuário: {e.message_dict}", exc_info=True)
             raise DRFValidationError(e.message_dict)
        except Exception as e:
            logger.error(f"Erro inesperado ao criar usuário: {e}", exc_info=True)
            raise DRFValidationError({"detail": str(e)})

class UserSerializer(DjoserUserSerializer):
    """Serializer para exibição de usuários, estendendo o do Djoser."""
    # Adiciona campos customizados para exibição
    is_admin = serializers.BooleanField(read_only=True)

    class Meta(DjoserUserSerializer.Meta):
        model = User
        fields = DjoserUserSerializer.Meta.fields + (
            'name', 'cnpj', 'celular',
            'is_admin', 'is_active', 'cpf', 'is_pessoa_juridica', 'cnpj'
        )

        def validate_name(self, value):
            """Sanitizar input do nome"""
            return escape(value)
    
        def validate_celular(self, value):
            """Validar formato de celular"""
            import re
            
            if not re.match(r'^\+?1?\d{9,15}$', value):
                raise serializers.ValidationError("Formato de celular inválido")
            return value

class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para atualização de usuários.
    Para admins, o Djoser ViewSet padrão permite mais campos.
    Este serializer é usado especificamente pelo CustomUserViewSet.update
    quando self.action == 'me' e o método é PUT/PATCH.
    """
    # Campos explicitamente editáveis - somente estes serão processados
    celular = serializers.CharField(required=False)

    # Campos somente leitura - serão ignorados se enviados
    email = serializers.EmailField(read_only=True)
    name = serializers.CharField(read_only=True)
    cnpj = serializers.CharField(read_only=True)
    cpf = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_admin = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            'celular',
            # Campos somente leitura
            'email', 'name', 'cnpj', 'is_active',
            'is_admin', 'cpf',
        )

    def validate_celular(self, value):
        """Valida o formato do número de celular."""
        # Remover caracteres não numéricos
        value = ''.join(filter(str.isdigit, value))
        if len(value) != 11:
            raise serializers.ValidationError("O celular deve conter 11 dígitos.")
        return value

    def validate(self, attrs):
        """
        Validação principal dos dados.
        """
        # Verificar dados da requisição diretamente
        request_data = self.initial_data
        allowed_fields = {'celular',}

        # Verificar campos não permitidos
        for field in request_data:
            if field not in allowed_fields:
                raise serializers.ValidationError({
                    field: f"Você não tem permissão para alterar este campo."
                })
        return attrs

    def to_internal_value(self, data):
        """
        Sobrescreve para garantir que campos não permitidos serão ignorados
        antes da validação, aumentando a segurança.
        """
        # Filtragem inicial - remove campos não permitidos antes da validação
        allowed_fields = {'celular',}
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

        # Chama implementação padrão com dados filtrados
        return super().to_internal_value(filtered_data)

    def update(self, instance, validated_data):
        """
        Sobrescreve o método update para aplicar as atualizações.
        O ModelSerializer já lida com a atualização dos campos presentes
        em validated_data que estão na Meta.fields.
        """
        # Campos permitidos para alteração
        allowed_fields = {'celular',}

        # Filtra novamente para garantir que apenas campos permitidos sejam usados
        filtered_data = {k: v for k, v in validated_data.items() if k in allowed_fields}

        # Atualiza os campos um por um para maior controle
        for field, value in filtered_data.items():
            setattr(instance, field, value)

        # Normaliza o número de celular antes de salvar
        if 'celular' in filtered_data:
            instance.celular = ''.join(filter(str.isdigit, instance.celular))

        # Se estivermos em um contexto de requisição, podemos capturar o usuário para o históric
        for attr, value in validated_data.items():
            setattr(instance, attr, value)


        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            instance._history_user = request.user

        instance.save()
        logger.info(f"Usuário {instance.email} atualizado por {request.user.email if request else 'sistema'}")
        return instance

class CustomUserDeleteSerializer(UserDeleteSerializer):
    # O campo current_password já é definido no UserDeleteSerializer base.
    # Precisamos sobrescrevê-lo para modificar seu comportamento.
    current_password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user.is_staff: # ou request.user.is_superuser, dependendo da sua definição de admin
            # Se o usuário é admin, não exigimos a senha atual
            # Removemos o campo para que a validação base não falhe por ele estar ausente
            attrs.pop('current_password', None)
            return attrs
        else:
            # Se não for admin, a validação padrão do Djoser para current_password será aplicada
            # O UserDeleteSerializer base já faz a validação da senha
            return super().validate(attrs)

class UserDetailSerializer(serializers.ModelSerializer):
    """
    Serializer para exibir detalhes de usuários, incluindo propriedades customizadas
    e campos relacionados.
    """
    # Campos de propriedade (ReadOnlyField para que não sejam editáveis via API)
    is_admin = serializers.ReadOnlyField()
    is_tecnico = serializers.ReadOnlyField()
    is_cliente = serializers.ReadOnlyField()

    # Para campos relacionados como 'groups', é melhor usar SlugRelatedField
    # para exibir os nomes dos grupos em vez dos IDs.
    groups = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field='name' # Exibe o nome do grupo
    )

    class Meta:
        model = User
        fields = '__all__'

class ClientListSerializer(serializers.ModelSerializer):
    """
    Serializer específico para listar clientes.
    Retorna apenas informações relevantes, sem dados sensíveis.
    """
    groups = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'uuid',
            'email',
            'name',
            'cnpj',
            'cpf',
            'celular',
            'is_pessoa_juridica',
            'is_active',
            'is_admin',
            'is_tecnico',
            'is_cliente',
            'groups',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields  # Todos os campos são read-only

    def get_groups(self, obj):
        """Retorna lista de nomes dos grupos do usuário"""
        return [group.name for group in obj.groups.all()]
