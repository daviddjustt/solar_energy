import os
from decimal import Decimal
from rest_framework import serializers
from solar.services.models import ServiceType, ServiceRequest
from solar.users.models import User  # Importe o modelo de utilizador correto
from django.contrib.auth import get_user_model
from rest_framework import serializers
from solar.documents.serializers import AbstractDocumentUploadSerializer, AbstractPaymentDocumentSerializer
from .models import ServiceRequest, ServiceAttachment, ServicePendency, ServiceObservation, ServiceStatusHistory, ServiceUnit

User = get_user_model()

class ServiceAttachmentSerializer(AbstractDocumentUploadSerializer):
    service = serializers.PrimaryKeyRelatedField(read_only=True)
    enviado_por_nome = serializers.CharField(source='enviado_por.get_full_name', read_only=True)
    
    # R3b: Forçamos a validação de status pelas opções do modelo para fechar a brecha de segurança.
    status = serializers.ChoiceField(choices=ServiceAttachment.STATUS_CHOICES, required=False)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)

    class Meta(AbstractDocumentUploadSerializer.Meta):
        model = ServiceAttachment
        fields = AbstractDocumentUploadSerializer.Meta.fields + [
            'service', 'categoria', 'enviado_por', 'enviado_por_nome',
            'pendencia', 'unidade', 'status', 'rejection_reason'
        ]
        read_only_fields = AbstractDocumentUploadSerializer.Meta.read_only_fields + ['enviado_por', 'approved_at']
        download_endpoint_name = 'api:service-attachment-download'
        parent_lookup_field = 'service_id'


    def validate_arquivo(self, value):
        ""
        from documents.utils import validate_file_size, validate_file_extension
        from django.core.exceptions import ValidationError as DjangoValidationError

        if value:
            try:
                # Dispara as funções exatas do seu ArquivoMixin
                validate_file_size(value)
                validate_file_extension(value)
            except DjangoValidationError as e:
                # Converte o erro do Django Model para o erro do DRF
                raise serializers.ValidationError(e.messages)
        return value
    
    def validate(self, data):
        data = super().validate(data)
        request = self.context.get('request')
        user = request.user
        service = self.context.get('parent') or (self.instance.service if self.instance else None)

        # Definição precisa e imune à falha default=True do R4
        is_cliente = getattr(user, 'is_cliente', False) and not (user.is_superuser or getattr(user, 'is_admin', False))

        # R9: Validação forte do boleto
        related_payment_document = data.get('related_payment_document')
        if related_payment_document:
            if related_payment_document.categoria != ServiceAttachment.CategoriaChoices.BOLETO:
                raise serializers.ValidationError({'related_payment_document': "O documento relacionado deve ser obrigatoriamente um BOLETO."})
            if related_payment_document.service != service:
                raise serializers.ValidationError({'related_payment_document': "O boleto selecionado pertence a outra solicitação."})

        # R4: Valida se Pendência e Unidade pertencem à mesma solicitação
        if data.get('pendencia') and data.get('pendencia').service != service:
            raise serializers.ValidationError({'pendencia': "Esta pendência pertence a outro serviço."})
        if data.get('unidade') and data.get('unidade').service != service:
            raise serializers.ValidationError({'unidade': "Esta unidade pertence a outro serviço."})

        # R4: Reenvio pelo cliente só pode alterar o arquivo
        if self.instance and is_cliente:
            campos_bloqueados = ['document_name', 'document_type', 'categoria', 'pendencia', 'unidade', 'related_payment_document']
            for campo in campos_bloqueados:
                if campo in data and data.get(campo) != getattr(self.instance, campo):
                    raise serializers.ValidationError({campo: "Clientes não podem alterar este campo durante o reenvio de um anexo reprovado."})

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

class ServiceUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceUnit
        fields = '__all__'
        read_only_fields = ['service']

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
    service = serializers.PrimaryKeyRelatedField(read_only=True)
    autor = serializers.PrimaryKeyRelatedField(read_only=True)
    autor_nome = serializers.CharField(source='autor.get_full_name', read_only=True)
    
    class Meta:
        model = ServiceObservation
        fields = ['id', 'service', 'autor', 'autor_nome', 'texto', 'created_at', 'updated_at']
        read_only_fields = ['id', 'service', 'autor', 'created_at', 'updated_at']

    def validate_texto(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("O texto da observação não pode estar em branco.")
        return value.strip()

class ServiceRequestSerializer(serializers.ModelSerializer):
    tipo_detalhe = ServiceTypeSerializer(source='tipo', read_only=True)
    
    # --- INÍCIO DA RESOLUÇÃO DO R7 ---
    # Removemos o read_only=True para que o DRF passe a aceitar a lista no payload
    unidades = ServiceUnitSerializer(many=True, required=False)

    class Meta:
        model = ServiceRequest
        read_only_fields = ['solicitante', 'status', 'executor', 'valor_cobrado', 'payment_status', 'motivo_reprova']
        fields = '__all__'

    def validate(self, data):
        unidades = data.get('unidades', [])
        rateio = data.get('modalidade_rateio')
        
        if unidades:
            geradoras = [u for u in unidades if u.get('papel') == 'GERADORA']
            if len(geradoras) != 1:
                raise serializers.ValidationError({'unidades': "É obrigatória exatamente uma unidade GERADORA."})
                
            if rateio == ServiceRequest.RateioChoices.PORCENTAGEM:
                beneficiarias = [u for u in unidades if u.get('papel') == 'BENEFICIARIA']
                soma = sum((u.get('porcentagem') or Decimal('0')) for u in beneficiarias)
                if beneficiarias and soma != Decimal('100.00'):
                    raise serializers.ValidationError({'unidades': "A soma das porcentagens das beneficiárias deve ser 100%."})
        
        return data
    
    def create(self, validated_data):
        # 1. Removemos (pop) as unidades do dicionário antes de guardar o serviço
        unidades_data = validated_data.pop('unidades', [])
        
        tipo = validated_data['tipo']
        validated_data['valor_cobrado'] = tipo.valor
        
        # 2. Criamos o serviço principal
        service = super().create(validated_data)
        
        # 3. Iteramos sobre a lista e guardamos cada unidade associada ao novo serviço
        for unidade_data in unidades_data:
            ServiceUnit.objects.create(service=service, **unidade_data)
            
        return service

    def update(self, instance, validated_data):
        # Tratamento de unidades também na atualização (PUT/PATCH)
        unidades_data = validated_data.pop('unidades', None)
        
        instance = super().update(instance, validated_data)
        
        if unidades_data is not None:
            # Abordagem de substituição total: apaga as antigas e recria as novas
            instance.unidades.all().delete()
            for unidade_data in unidades_data:
                ServiceUnit.objects.create(service=instance, **unidade_data)
                
        return instance