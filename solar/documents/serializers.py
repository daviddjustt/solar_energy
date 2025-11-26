from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from .models import ClientProject, ConsumerUnit, ProjectDocument, ListaDeMateriais
from .utils import VOLTAGEM_LABELS, VOLTAGEM_MAP
from solar.files.utils import DOCUMENT_TYPE_CHOICES

class VoltageField(serializers.CharField):
    """
    Campo customizado que converte o 'value' do frontend (ex: "127")
    para o 'label' completo (ex: "Monofásico - 127V") antes da validação do modelo.
    """

    def to_internal_value(self, data):
        """
        Este método é chamado pelo DRF para converter o dado de entrada (frontend)
        para o formato interno (para o modelo).
        """
        if not data:
            raise serializers.ValidationError("Voltagem é obrigatória")

        value_str = str(data).strip()

        # 1. Tenta converter o 'value' curto (ex: "127") para o 'label' completo
        converted_label = VOLTAGEM_MAP.get(value_str)

        if converted_label:
            return converted_label # Retorna o label completo

        # 2. Se não foi um 'value' curto, verifica se já é um 'label' completo (para updates ou dados diretos)
        # Isso é importante para que o campo aceite o valor já salvo no banco
        valid_model_choices = [choice[0] for choice in ClientProject.VOLTAGEM_CHOICES]
        if value_str in valid_model_choices:
            return value_str

        # 3. Se não encontrou, é um valor inválido
        valid_short_values = ', '.join(VOLTAGEM_MAP.keys())
        valid_full_labels = ', '.join(valid_model_choices)
        raise serializers.ValidationError(
            f"Voltagem inválida. Valores aceitos (curtos): {valid_short_values}. "
            f"Valores aceitos (completos): {valid_full_labels}. "
            f"Você enviou: '{value_str}'"
        )

    def to_representation(self, value):
        """
        Este método é chamado pelo DRF para converter o dado interno (modelo)
        para o formato de saída (frontend). Retorna o label completo.
        """
        return str(value)

# Serializer para Unidades Consumidoras
class ConsumerUnitSerializer(serializers.ModelSerializer):
    prioridade_is_porcentagem = serializers.BooleanField()
    
    class Meta:
        model = ConsumerUnit
        fields = "__all__"
        read_only_fields = ['project']
    
    def validate(self, data):
        """
        Valida que se 'prioridade_is_porcentagem' for True,
        'porcentagem' não pode ser nulo, vazio ou branco.
        """
        priority_level = data.get('priority_level')
        prioridade_is_porcentagem = data.get('prioridade_is_porcentagem')
        porcentagem = data.get('porcentagem')

        # Se prioridade_is_porcentagem for True, então porcentagem é obrigatório
        if prioridade_is_porcentagem is False:
            if priority_level is None or priority_level == '':
                raise serializers.ValidationError({
                    'priority_level': 'O campo "priority_level" não pode ser vazio, nulo ou branco quando "prioridade_is_porcentagem" é True.'
                })
            if porcentagem is not None and porcentagem != '':
                raise serializers.ValidationError({
                    'porcentagem': 'O campo "porcentagem" deve ser nulo ou vazio quando "prioridade_is_porcentagem" é True.'
                })
            
        elif prioridade_is_porcentagem is True:
            if porcentagem is None or porcentagem == '':
                raise serializers.ValidationError({
                    'porcentagem': 'O campo "porcentagem" não pode ser vazio, nulo ou branco quando "prioridade_is_porcentagem" é False.'
                })
            if priority_level is not None and priority_level != '':
                raise serializers.ValidationError({
                    'priority_level': 'O campo "priority_level" deve ser nulo ou vazio quando "prioridade_is_porcentagem" é False.'
                })
        return data

        
class ListaDeMateriaisSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaDeMateriais
        fields = "__all__"
        read_only_fields = ['project']

# Serializer para Upload de Documentos

class DocumentUploadSerializer(serializers.ModelSerializer):
    """
    Serializer para upload de documentos em projetos.
    Gerencia permissões por tipo de usuário e tipo de documento.
    """

    # Campos read-only (se existirem no modelo)
    project = serializers.PrimaryKeyRelatedField(read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    approved_at = serializers.DateTimeField(read_only=True)

    # Se o modelo tiver propriedades customizadas, adicione aqui:
    # days_since_upload = serializers.IntegerField(read_only=True)
    # is_recent = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProjectDocument
        fields = "__all__"
        read_only_fields = [
            'is_approved', 
            'project',
            'created_at',
            'updated_at',
            'approved_at',
        ]

    def validate_document_type(self, value):
        """
        ✅ Validação básica do tipo de documento.
        """
        valid_types = [choice[0] for choice in DOCUMENT_TYPE_CHOICES]

        if value not in valid_types:
            raise serializers.ValidationError(
                f"Tipo de documento inválido. Escolha entre: {', '.join(valid_types)}"
            )

        return value

    def validate_related_payment_document(self, value):
        """
        ✅ Converte valores inválidos (0, "0", "") para None.
        Só use este método se o modelo ProjectDocument tiver este campo.
        """
        if value in [0, '0', '']:
            return None

        return value

    def validate(self, data):
        """
        ✅ VALIDAÇÃO CONSOLIDADA - Todas as regras de negócio aqui.
        Executa DEPOIS de todas as validações de campo individual.
        """
        request = self.context.get('request')
        user = request.user if request else None

        if not user:
            raise serializers.ValidationError(
                "Usuário não autenticado. Faça login para realizar esta operação."
            )

        # Pega o document_type (pode estar em data ou na instância durante update)
        document_type = data.get('document_type')
        if self.instance and not document_type:
            document_type = self.instance.document_type

        # ===== VALIDAÇÃO DE PERMISSÕES POR TIPO DE DOCUMENTO =====

        # 🔒 REGRA 1: Clientes NÃO podem criar/editar boletos
        if user.is_cliente and document_type == 'boleto':
            raise serializers.ValidationError({
                'document_type': 
                    'Clientes não têm permissão para criar ou editar boletos. '
                    'Esta operação é restrita a administradores e técnicos.'
            })

        # 🔒 REGRA 2: Apenas Admin, Técnico e Superuser podem criar boletos
        if document_type == 'boleto':
            if not (user.is_admin or user.is_tecnico or user.is_superuser):
                raise serializers.ValidationError({
                    'document_type': 
                        'Apenas administradores e técnicos podem criar boletos. '
                        f'Seu perfil atual: {user.get_user_type_display()}.'
                })

        # ===== VALIDAÇÃO DE COMPROVANTE DE PAGAMENTO (se aplicável) =====

        # 🔒 REGRA 3: Comprovantes de pagamento DEVEM ter boleto relacionado
        if document_type == 'comprovante_de_pagamento':
            related_payment_document = data.get('related_payment_document')

            # Durante update, verifica na instância
            if self.instance and not related_payment_document:
                related_payment_document = self.instance.related_payment_document

            if not related_payment_document:
                raise serializers.ValidationError({
                    'related_payment_document': [
                        'Este campo é obrigatório para comprovantes de pagamento.',
                        'Informe o ID do boleto/fatura que este comprovante está quitando.',
                        'Para listar os boletos disponíveis, acesse: GET /projects/{id}/documents/?document_type=boleto'
                    ]
                })

        return data

    def create(self, validated_data):
        """
        ✅ Sobrescreve create para injetar o project do contexto.
        """
        project = self.context.get('project_pk')

        if not project:
            raise serializers.ValidationError(
                "O projeto deve ser fornecido no contexto para criar um documento."
            )

        validated_data['project_pk'] = project
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """
        ✅ Sobrescreve update para prevenir alteração do project.
        """
        # Remove 'project' se alguém tentar alterá-lo
        validated_data.pop('project', None)

        return super().update(instance, validated_data)
# Serializer para as informações básicas do Projeto
class ProjectInfoSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    voltagem = VoltageField()
    voltagem_label = serializers.SerializerMethodField()
    
    class Meta:
        model = ClientProject
        fields = "__all__" # 'codigoCliente' será incluído aqui automaticamente do request body
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'valor_total', 'resumo_financeiro')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        read_only_fields = ['created_by', 'created_at', 'updated_at']
        for field_name in read_only_fields:
            if field_name in self.fields:
                self.fields[field_name].read_only = True

    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem
    
    
    def to_representation_user(self, instance):
        """Customiza a representação para incluir informações do usuário"""
        data = super().to_representation_user(instance)
        if instance.created_by:
            data['created_by_info'] = {
                'uuid': str(instance.created_by.uuid),
                'name': instance.created_by.name,
                'email': instance.created_by.email
            }
        return data

    def validate_tipoDocumento(self, value):
        if value :
            return value

    def validate_documents(self, data):
        tipo_documento = data.get('tipoDocumento', '').lower()
        documento = data.get('client_document')

        if tipo_documento == 'cpf':
            data['tipoDocumento'] = 'PF'
            if documento:
                import re
                if not re.match(r'^\d{3}\.\d{3}\.\d{3}-\d{2}$', documento):
                    raise serializers.ValidationError({
                        'client_document': 'CPF deve estar no formato XXX.XXX.XXX-XX'
                    })
        elif tipo_documento == 'PJ':
            data['tipoDocumento'] = 'PJ'
            if documento:
                import re
                if not re.match(r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$', documento):
                    raise serializers.ValidationError({
                        'client_document': 'CNPJ deve estar no formato XX.XXX.XXX/XXXX-XX'
                    })
        else:
            if documento:
                raise serializers.ValidationError({'tipoDocumento': 'Tipo de documento é obrigatório quando o documento é fornecido.'})

        # Validação de coordenadas atualizada conforme seu código
        lat_fields = [data.get('lat_degrees'), data.get('lat_minutes'), data.get('lat_seconds')]
        long_fields = [data.get('long_degrees'), data.get('long_minutes'), data.get('long_seconds')]

        if any(f is not None for f in lat_fields) and not all(f is not None for f in lat_fields):
            raise serializers.ValidationError({
                'coordinates': 'Todos os campos de latitude (graus, minutos, segundos) devem ser fornecidos se algum for.'
            })
        if any(f is not None for f in long_fields) and not all(f is not None for f in long_fields):
            raise serializers.ValidationError({
                'coordinates': 'Todos os campos de longitude (graus, minutos, segundos) devem ser fornecidos se algum for.'
            })
        return data

    def create(self, validated_data):
        validated_data.pop('tipoDocumento', None)
        project = ClientProject.objects.create(**validated_data)
        return project

    def update(self, instance, validated_data):
        validated_data.pop('tipoDocumento', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem    

# Serializer para Listagem de Projetos
class ProjectListSerializer(serializers.ModelSerializer):
    codigoCliente = serializers.CharField(read_only=True)
    nomeTitular = serializers.CharField( read_only=True)
    classe = serializers.CharField( read_only=True)
    celular = serializers.CharField( read_only=True)
    tipoDocumento = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()
    consumer_units_count = serializers.SerializerMethodField()
    voltagem = VoltageField()

    class Meta:
        model = ClientProject
        fields = "__all__"
    

    def get_tipoDocumento(self, obj):
        return 'cpf' if obj.tipoDocumento == 'PF' else 'PJ'

    def get_documents_count(self, obj):
        return obj.documents.count()

    def get_consumer_units_count(self, obj):
        return obj.consumer_units.count()

     
    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem
    
class TecnicoClientProjectSerializer(serializers.ModelSerializer):
    """Serializer para técnicos e clientes - campos financeiros são read-only"""
    
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    voltagem = VoltageField()
    
    class Meta:
        model = ClientProject
        fields = '__all__'
        read_only_fields = (
            'created_by', 'created_at', 'updated_at', 
        )
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        read_only_fields = ['created_by', 'created_at', 'updated_at']
        for field_name in read_only_fields:
            if field_name in self.fields:
                self.fields[field_name].read_only = True
    
    
    def validate(self, data):
        """Validação para impedir modificação de campos financeiros por técnicos/clientes"""
        user = self.context['request'].user
        
        # Verificar se é um técnico ou cliente tentando modificar campos financeiros
        if user.groups.filter(name__in=['Tecnicos', 'Clientes']).exists():
            financial_fields = ['tipo_financeiro', 'valor_financeiro', 'parcelas']
            
            for field in financial_fields:
                if field in data:
                    raise serializers.ValidationError({
                        field: 'Usuários do tipo Técnico ou Cliente não podem modificar campos financeiros.'
                    })
        
        return data
    
    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem
    
# Serializer específico para documentos de pagamento
class PaymentDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDocument
        fields = '__all__'
        read_only_fields = ['status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            
            # Se for cliente, só pode criar/editar comprovante
            if user.is_cliente:
                if self.instance and self.instance.document_type == 'boleto':
                    # Cliente não pode editar boleto
                    for field in self.fields:
                        if field != 'id':
                            self.fields[field].read_only = True

