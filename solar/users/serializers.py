import logging
import re

# Django CORE
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _

# Third-party imports
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from djoser.serializers import UserSerializer as DjoserUserSerializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError

# Local application imports
from .models import User
from djoser.serializers import TokenCreateSerializer
from django.contrib.auth import authenticate


logger = logging.getLogger(__name__)

class UserCreateSerializer(DjoserUserCreateSerializer):
    """Serializer para criação de usuários com tratamento especial."""

    class Meta(DjoserUserCreateSerializer.Meta):
        model = User
        fields = tuple(set(DjoserUserCreateSerializer.Meta.fields + (
            'name', 'cpf', 'celular', 'patent', 'photo'
        )))
        extra_kwargs = {
            'cpf': {'required': True},
            'celular': {'required': True},
            'name': {'required': True},
            # 'password' já é required por padrão no DjoserUserCreateSerializer
        }

    def validate(self, attrs):
        """Validação global com normalização de dados."""
        attrs = super().validate(attrs)
        # Normalização de campos
        attrs['name'] = attrs.get('name', '').strip().upper()
        attrs['cpf'] = re.sub(r'\D', '', attrs.get('cpf', '')) # Remove não dígitos
        attrs['celular'] = re.sub(r'\D', '', attrs.get('celular', '')) # Remove não dígitos

        # Validação de CPF (exemplo básico, considere uma validação mais robusta)
        if len(attrs['cpf']) != 11:
             raise DRFValidationError({"cpf": _("CPF deve conter 11 dígitos numéricos.")})

        # Validação de Celular (exemplo básico)
        if len(attrs['celular']) != 11:
             raise DRFValidationError({"celular": _("Celular deve conter 11 dígitos numéricos (DDD + número).")})


        # Validação adicional se necessário (ex: unicidade de CPF/celular se não for tratada no modelo)
        # if User.objects.filter(cpf=attrs['cpf']).exists():
        #     raise DRFValidationError({"cpf": _("Já existe um usuário com este CPF.")})
        # if User.objects.filter(celular=attrs['celular']).exists():
        #      raise DRFValidationError({"celular": _("Já existe um usuário com este celular.")})


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
    photo_url = serializers.SerializerMethodField()
    # Adiciona campos customizados para exibição
    is_admin = serializers.BooleanField(read_only=True)
    is_operacoes = serializers.BooleanField(read_only=True)
    is_sac = serializers.BooleanField(read_only=True)
    sac_profile = serializers.CharField(source='get_sac_profile_display', read_only=True) # Exibe o label da escolha


    class Meta(DjoserUserSerializer.Meta):
        model = User
        fields = DjoserUserSerializer.Meta.fields + (
            'name', 'cpf', 'celular', 'patent', 'photo', 'photo_url',
            'is_admin', 'is_operacoes', 'is_sac', 'sac_profile', 'is_active' # Inclui as flags e perfil SAC
        )
        # Campos que podem ser lidos mas não alterados via este serializer (embora Djoser controle isso)
        read_only_fields = DjoserUserSerializer.Meta.read_only_fields + (
             'is_admin', 'is_operacoes', 'is_sac', 'sac_profile', 'is_active'
        )

    def get_photo_url(self, obj):
        """Retorna a URL da foto se existir."""
        if obj.photo and hasattr(obj.photo, 'url'):
            return obj.photo.url
        return None

class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para atualização de usuários.
    Garanto estritamente que apenas celular e photo possam ser atualizados
    pelo endpoint 'me' para usuários comuns.
    Para admins, o Djoser ViewSet padrão permite mais campos.
    Este serializer é usado especificamente pelo CustomUserViewSet.update
    quando self.action == 'me' e o método é PUT/PATCH.
    """
    # Campos explicitamente editáveis - somente estes serão processados
    celular = serializers.CharField(required=False)
    photo = serializers.ImageField(required=False)

    # Campos somente leitura - serão ignorados se enviados
    email = serializers.EmailField(read_only=True)
    name = serializers.CharField(read_only=True)
    cpf = serializers.CharField(read_only=True)
    patent = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_admin = serializers.BooleanField(read_only=True)
    is_operacoes = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            'celular', 'photo',
            # Campos somente leitura
            'email', 'name', 'cpf', 'patent', 'is_active',
            'is_admin', 'is_operacoes'
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
        allowed_fields = {'celular', 'photo'}

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
        allowed_fields = {'celular', 'photo'}
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
        allowed_fields = {'celular', 'photo'}

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

class SpecialCPFTokenCreateSerializer(serializers.Serializer):
    cpf = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        cpf = attrs.get('cpf')
        password = attrs.get('password')

        if not cpf or not password:
            raise serializers.ValidationError('CPF e senha são obrigatórios.')

        # Usa o backend especial para CPF
        from .backends import SpecialCPFBackend
        backend = SpecialCPFBackend()

        self.user = backend.authenticate(
            request=self.context.get('request'),
            username=cpf,
            password=password,
        )

        if not self.user:
            raise serializers.ValidationError(
                'CPF não encontrado, senha incorreta ou usuário sem acesso especial.'
            )

        if not self.user.is_active:
            raise serializers.ValidationError('Conta inativa.')

        return attrs
