import os
from decimal import Decimal
from rest_framework import serializers
from solar.services.models import ServiceType, ServiceRequest
from solar.users.models import User  # Importe o modelo de utilizador correto
from django.contrib.auth import get_user_model
from rest_framework import serializers
from solar.documents.serializers import AbstractDocumentUploadSerializer, AbstractPaymentDocumentSerializer
from solar.documents.utils import validate_file_size, validate_file_extension
from .models import ServiceRequest, ServiceAttachment, ServicePendency, ServiceObservation, ServiceStatusHistory, ServiceUnit

User = get_user_model()

class ServiceAttachmentSerializer(AbstractDocumentUploadSerializer):
    service = serializers.PrimaryKeyRelatedField(read_only=True)
    enviado_por_nome = serializers.CharField(source='enviado_por.get_full_name', read_only=True)
    
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
        if value:
            try:
                validate_file_size(value)
                validate_file_extension(value)
            except DjangoValidationError as e:
                raise serializers.ValidationError(list(e.messages))
        return value

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

        # --- R4 e R11: Deteção forte de cliente ---
        is_cliente = getattr(user, 'is_cliente', False) and not (
            user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_externo', False)
        )

        # --- R11: Restaurar regras de categoria por perfil ---
        categorias_cliente = [
            ServiceAttachment.CategoriaChoices.SOLICITACAO, 
            ServiceAttachment.CategoriaChoices.PENDENCIA_CLIENTE, 
            ServiceAttachment.CategoriaChoices.COMPROVANTE
        ]
        categorias_equipe = [
            ServiceAttachment.CategoriaChoices.PENDENCIA_EQUIPE, 
            ServiceAttachment.CategoriaChoices.OBSERVACAO, 
            ServiceAttachment.CategoriaChoices.RESULTADO, 
            ServiceAttachment.CategoriaChoices.BOLETO
        ]

        if is_cliente and categoria not in categorias_cliente:
            raise serializers.ValidationError({'categoria': f"Clientes não podem enviar arquivos da categoria '{categoria}'."})

        if not is_cliente and not self.instance and categoria not in categorias_equipe:
            raise serializers.ValidationError({'categoria': f"A equipa não pode enviar arquivos da categoria '{categoria}'."})

        # --- R11 e R4: Restaurar regra de reenvio do cliente ---
        if self.instance and is_cliente:
            if self.instance.status != ServiceAttachment.STATUS_REJECTED:
                raise serializers.ValidationError("Clientes só podem reenviar anexos que foram explicitamente rejeitados.")
            
            # Garante que o cliente só altera o ficheiro, preservando o resto
            campos_bloqueados = ['document_name', 'document_type', 'categoria', 'pendencia', 'unidade', 'related_payment_document']
            for campo in campos_bloqueados:
                if campo in data and data.get(campo) != getattr(self.instance, campo):
                    raise serializers.ValidationError({campo: "Clientes não podem alterar este campo durante o reenvio de um anexo reprovado."})

        # --- R9: Validação do boleto ---
        related_payment_document = data.get('related_payment_document')
        if related_payment_document:
            if related_payment_document.categoria != ServiceAttachment.CategoriaChoices.BOLETO:
                raise serializers.ValidationError({'related_payment_document': "O documento relacionado deve ser obrigatoriamente um BOLETO."})
            if related_payment_document.service != service:
                raise serializers.ValidationError({'related_payment_document': "O boleto selecionado pertence a outra solicitação."})

        # --- R4: Valida se Pendência e Unidade pertencem à mesma solicitação ---
        if data.get('pendencia') and data.get('pendencia').service != service:
            raise serializers.ValidationError({'pendencia': "Esta pendência pertence a outro serviço."})
        if data.get('unidade') and data.get('unidade').service != service:
            raise serializers.ValidationError({'unidade': "Esta unidade pertence a outro serviço."})

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

        modalidade_rateio = data.get('modalidade_rateio')
        unidades_data = data.get('unidades', [])
        
        # Se houver unidades na requisição e a modalidade for PRIORIDADE
        if unidades_data and modalidade_rateio == 'PRIORIDADE':
            prioridades_beneficiarias = []
            
            for unidade in unidades_data:
                papel = unidade.get('papel')
                prioridade = unidade.get('prioridade')
                
                if papel == 'GERADORA':
                    # A geradora é fixa na prioridade 0
                    if prioridade != 0:
                        raise serializers.ValidationError(
                            {"unidades": "A unidade GERADORA deve estar fixa na prioridade 0."}
                        )
                elif papel == 'BENEFICIARIA':
                    if prioridade is None or prioridade <= 0:
                        raise serializers.ValidationError(
                            {"unidades": "Todas as unidades BENEFICIÁRIAS devem ter uma prioridade válida informada (1, 2, 3...)."}
                        )
                    prioridades_beneficiarias.append(prioridade)

            # Verifica se as prioridades das beneficiárias formam uma sequência perfeita sem lacunas (ex: 1, 2, 3)
            if prioridades_beneficiarias:
                prioridades_beneficiarias.sort()
                sequencia_esperada = list(range(1, len(prioridades_beneficiarias) + 1))
                
                if prioridades_beneficiarias != sequencia_esperada:
                    raise serializers.ValidationError(
                        {"unidades": f"As prioridades das unidades beneficiárias devem ser sequenciais, sem repetição ou lacunas. Encontrado: {prioridades_beneficiarias}. Esperado: {sequencia_esperada}."}
                    )
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