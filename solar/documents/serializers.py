from rest_framework import serializers
from .models import ClientProject, ConsumerUnit, ProjectDocument

# Serializer para Unidades Consumidoras
class ConsumerUnitSerializer(serializers.ModelSerializer):
    # codigoCliente = serializers.CharField(source='client_code')

    class Meta:
        model = ConsumerUnit
        fields = ["percentage","tensao","client_code",]
        """
            {
            "porcentagem": "",
            "tensao": "string",
            "percentage": "-76.93",
            "voltage": "string",
            "project": 0
            }
        """

# Serializer para Upload de Documentos
class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDocument
        fields = "__all__"
        read_only_fields = [
            'uploaded_at', 'is_approved', 'rejection_reason', 'project',
        ]

# Serializer para as informações básicas do Projeto
class ProjectInfoSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    valor_total = serializers.ReadOnlyField()
    resumo_financeiro = serializers.ReadOnlyField()

    class Meta:
        model = ClientProject
        fields = "__all__" # 'client_code' será incluído aqui automaticamente do request body
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'valor_total', 'resumo_financeiro')
    
    def validate_money(self, data):
        """Validação customizada no serializer"""
        tipo_financeiro = data.get('tipo_financeiro')
        parcelas = data.get('parcelas')
        valor_financeiro = data.get('valor_financeiro')

        # Validar parcelas para mensalidade
        if tipo_financeiro == 'mensalidade':
            if not parcelas or parcelas <= 0:
                raise serializers.ValidationError({
                    'parcelas': 'Número de parcelas é obrigatório e deve ser maior que zero para mensalidade.'
                })
        else:
            # Se não for mensalidade, remove parcelas
            data['parcelas'] = None

        # Validar valor financeiro
        if not valor_financeiro or valor_financeiro <= 0:
            raise serializers.ValidationError({
                'valor_financeiro': 'Valor financeiro deve ser maior que zero.'
            })

        return data
    

    def to_representation_money(self, instance):
        """Customiza a representação para incluir informações financeiras"""
        data = super().to_representation_money(instance)
        
        # Informações do usuário criador
        if instance.created_by:
            data['created_by_info'] = {
                'uuid': str(instance.created_by.uuid),
                'name': instance.created_by.name,
                'email': instance.created_by.email
            }
        
        # Informações financeiras formatadas
        data['financeiro_info'] = {
            'tipo': instance.get_tipo_financeiro_display(),
            'valor_formatado': f"R$ {instance.valor_financeiro:,.2f}",
            'parcelas': instance.parcelas if instance.tipo_financeiro == 'mensalidade' else None,
            'valor_total_formatado': f"R$ {instance.valor_total:,.2f}",
            'resumo': instance.resumo_financeiro
        }
        
        return data

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
        if value and value.lower() not in ['cpf', 'cnpj']:
            raise serializers.ValidationError("Tipo de documento deve ser 'cpf' ou 'cnpj'.")
        return value

    def validate_documents(self, data):
        tipo_documento = data.get('tipoDocumento', '').lower()
        documento = data.get('client_document')

        if tipo_documento == 'cpf':
            data['client_type'] = 'PF'
            if documento:
                import re
                if not re.match(r'^\d{3}\.\d{3}\.\d{3}-\d{2}$', documento):
                    raise serializers.ValidationError({
                        'client_document': 'CPF deve estar no formato XXX.XXX.XXX-XX'
                    })
        elif tipo_documento == 'cnpj':
            data['client_type'] = 'PJ'
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

# Serializer para Listagem de Projetos
class ProjectListSerializer(serializers.ModelSerializer):
    codigoCliente = serializers.CharField(source='client_code', read_only=True)
    nomeTitular = serializers.CharField(source='project_holder_name', read_only=True)
    classe = serializers.CharField(source='project_class', read_only=True)
    celular = serializers.CharField(source='phone', read_only=True)
    tipoDocumento = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()
    consumer_units_count = serializers.SerializerMethodField()

    class Meta:
        model = ClientProject
        fields = [
            'id', 'codigoCliente', 'nomeTitular', 'classe', 'email', 'client_type',
            'tipoDocumento', 'celular', 'documentation_complete', 'documents_count',
            'consumer_units_count', 'created_at', 'updated_at'
        ]

    def get_tipoDocumento(self, obj):
        return 'cpf' if obj.client_type == 'PF' else 'cnpj'

    def get_documents_count(self, obj):
        return obj.documents.count()

    def get_consumer_units_count(self, obj):
        return obj.consumer_units.count()

class TecnicoClientProjectSerializer(serializers.ModelSerializer):
    """Serializer para técnicos e clientes - campos financeiros são read-only"""
    
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    valor_total = serializers.ReadOnlyField()
    resumo_financeiro = serializers.ReadOnlyField()
    
    # Campos financeiros como read-only para técnicos e clientes
    tipo_financeiro = serializers.CharField(read_only=True)
    valor_financeiro = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    parcelas = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = ClientProject
        fields = '__all__'
        read_only_fields = (
            'created_by', 'created_at', 'updated_at', 
            'valor_total', 'resumo_financeiro',
            'tipo_financeiro', 'valor_financeiro', 'parcelas'  # Campos financeiros
        )
    
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