from rest_framework import serializers
from solar.services.models import ServiceType, ServiceRequest
from solar.users.models import User  # Importe o modelo de utilizador correto
from django.contrib.auth import get_user_model
from rest_framework import serializers
from solar.documents.serializers import AbstractDocumentUploadSerializer, AbstractPaymentDocumentSerializer
from .models import ServiceRequest, ServiceAttachment, ServicePendency, ServiceObservation, ServiceStatusHistory

User = get_user_model()

class ServiceAttachmentSerializer(AbstractDocumentUploadSerializer):
    service = serializers.PrimaryKeyRelatedField(read_only=True)
    enviado_por_nome = serializers.CharField(source='enviado_por.get_full_name', read_only=True)

    class Meta(AbstractDocumentUploadSerializer.Meta):
        model = ServiceAttachment
        fields = AbstractDocumentUploadSerializer.Meta.fields + [
            'service', 'categoria', 'enviado_por', 'enviado_por_nome',
            'pendencia', 'unidade'
        ]
        read_only_fields = AbstractDocumentUploadSerializer.Meta.read_only_fields + ['enviado_por', 'status']
        download_endpoint_name = 'api:service-attachment-download'
        parent_lookup_field = 'service_id'

    def validate(self, data):
        data = super().validate(data)
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return data

        user = request.user
        service = self.context.get('parent') or (self.instance.service if self.instance else None)
        categoria = data.get('categoria') or (self.instance.categoria if self.instance else None)

        if not service:
            raise serializers.ValidationError("Serviço não identificado.")

        # --- RF-03 / REGRAS DE MATRIZ DE PERMISSÃO DE CATEGORIAS ---[cite: 10]
        categorias_cliente = ['SOLICITACAO', 'PENDENCIA_CLIENTE', 'COMPROVANTE_PAGAMENTO']
        categorias_equipe = ['PENDENCIA_EQUIPE', 'OBSERVACAO', 'RESULTADO', 'BOLETO']

        is_cliente = getattr(user, 'is_cliente', False) and not (user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_externo', False))
        
        if is_cliente and categoria not in categorias_cliente:
            raise serializers.ValidationError({'categoria': f"Clientes não podem enviar arquivos da categoria '{categoria}'."})

        if not is_cliente and categoria not in categorias_equipe:
            raise serializers.ValidationError({'categoria': f"A equipe não pode enviar arquivos da categoria '{categoria}'."})

        # --- REGRA DE REENVIO DO CLIENTE ---[cite: 10]
        if self.instance and is_cliente:
            if self.instance.status != ServiceAttachment.STATUS_REJECTED:
                raise serializers.ValidationError("Clientes só podem reenviar anexos que foram explicitamente rejeitados.")

        # --- COMPROVANTE SEM BOLETO (PIX) vs COM BOLETO ---[cite: 10]
        if categoria == 'COMPROVANTE_PAGAMENTO':
            related_payment = data.get('related_payment_document')
            if related_payment:
                if related_payment.categoria != 'BOLETO':
                    raise serializers.ValidationError({'related_payment_document': 'O documento vinculado deve ser um Boleto.'})
                if related_payment.service_id != service.id:
                    raise serializers.ValidationError({'related_payment_document': 'O boleto deve pertencer à mesma solicitação de serviço.'})

        return data

class ServiceStatusHistorySerializer(serializers.ModelSerializer):
    service = serializers.PrimaryKeyRelatedField(read_only=True)
    changed_by_nome = serializers.CharField(source='changed_by.get_full_name', read_only=True)

    class Meta:
        model = ServiceStatusHistory
        fields = [
            'id',
            'service',
            'old_status',
            'new_status',
            'changed_by',
            'changed_by_nome',
            'changed_at',
        ]
        # Como é apenas leitura, podemos colocar todos os campos como read_only
        read_only_fields = fields

class ServicePaymentDocumentSerializer(AbstractPaymentDocumentSerializer):
    class Meta(AbstractPaymentDocumentSerializer.Meta):
        model = ServiceAttachment

class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceType
        fields = '__all__'

class ExternalUserSerializer(serializers.ModelSerializer):
    """
    Serializer dedicado à criação e edição de Usuários Externos pelo Admin.
    """
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})
    tipos_servico = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=ServiceType.objects.all(),
        required=False
    )

    class Meta:
        model = User
        fields = (
            'uuid', 'name', 'email', 'celular', 'cpf', 
            'is_active', 'tipos_servico', 'password'
        )

    def validate_celular(self, value):
        """Valida e limpa o formato do número de celular."""
        value = ''.join(filter(str.isdigit, value))
        if len(value) != 11:
            raise serializers.ValidationError("O celular deve conter 11 dígitos.")
        return value

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        tipos = validated_data.pop('tipos_servico', [])

        # Força as regras de negócio para o Proxy Model Externo
        validated_data['is_externo'] = True
        validated_data['is_cliente'] = False
        validated_data['is_admin'] = False
        validated_data['is_tecnico'] = False
        validated_data['is_pessoa_juridica'] = False

        # Aproveita o UserManager para normalização e salvamento atômico
        user = User.objects.create_user(**validated_data)

        if password:
            user.set_password(password)
            user.save(update_fields=['password'])

        if tipos:
            user.tipos_servico.set(tipos)

        return user

    def update(self, instance, validated_data):
        # Proteção: Impede a alteração acidental ou intencional das flags base
        for flag in ['is_externo', 'is_cliente', 'is_admin', 'is_tecnico', 'is_pessoa_juridica']:
            validated_data.pop(flag, None)

        password = validated_data.pop('password', None)
        tipos = validated_data.pop('tipos_servico', None)

        if password:
            instance.set_password(password)
            instance.save(update_fields=['password'])

        if tipos is not None:
            instance.tipos_servico.set(tipos)

        # O ModelSerializer lida com o restante dos campos (name, celular, is_active)
        return super().update(instance, validated_data)

class ServicePendencySerializer(serializers.ModelSerializer):
    """
    Serializer para gestão de Pendências Nomeadas no módulo de Serviços.
    Traz aninhados os anexos associados (tanto a solicitação da equipe quanto a resposta do cliente).
    """
    service = serializers.PrimaryKeyRelatedField(read_only=True)
    criada_por = serializers.PrimaryKeyRelatedField(read_only=True)
    criada_por_nome = serializers.CharField(source='criada_por.get_full_name', read_only=True)
    
    # Exibe a lista de anexos vinculados a esta pendência
    anexos = ServiceAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ServicePendency
        fields = [
            'id',
            'service',
            'titulo',
            'observacao',
            'criada_por',
            'criada_por_nome',
            'status',
            'anexos',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 
            'service', 
            'criada_por', 
            'created_at', 
            'updated_at'
        ]

    def validate_status(self, value):
        status_validos = ['ABERTA', 'RESPONDIDA', 'RESOLVIDA']
        if value not in status_validos:
            raise serializers.ValidationError(
                f"Status inválido. Escolhas permitidas: {', '.join(status_validos)}"
            )
        return value

class ServiceObservationSerializer(serializers.ModelSerializer):
    """
    Serializer para gestão de Observações Livres no módulo de Serviços.
    Permite o registo de notas pela equipa e executores externos,
    exibindo a autoria e os anexos vinculados.
    """
    service = serializers.PrimaryKeyRelatedField(read_only=True)
    autor = serializers.PrimaryKeyRelatedField(read_only=True)
    autor_nome = serializers.CharField(source='autor.get_full_name', read_only=True)
    
    # Exibe a lista de anexos associados a esta observação (se houver)
    anexos = ServiceAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceObservation
        fields = [
            'id',
            'service',
            'autor',
            'autor_nome',
            'texto',
            'anexos',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'service',
            'autor',
            'created_at',
            'updated_at',
        ]

    def validate_texto(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("O texto da observação não pode estar em branco.")
        return value.strip()

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