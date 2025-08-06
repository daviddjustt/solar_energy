from rest_framework import serializers
from .models import ClientProject, ConsumerUnit, ProjectDocument

# Serializer para Unidades Consumidoras (mantido como está)
class ConsumerUnitSerializer(serializers.ModelSerializer):
    codigoCliente = serializers.CharField(source='client_code')
    porcentagem = serializers.DecimalField(source='percentage', max_digits=5, decimal_places=2, required=False)
    tensao = serializers.CharField(source='voltage', required=False)

    class Meta:
        model = ConsumerUnit
        fields = ['id', 'codigoCliente', 'porcentagem', 'tensao']

# Serializer para Upload de Documentos (mantido como está)
class DocumentUploadSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProjectDocument
        fields = "__all__"
        read_only_fields = [
            'uploaded_at', 'is_approved', 'rejection_reason',
        ]

# NOVO Serializer para as informações básicas do Projeto
class ProjectInfoSerializer(serializers.ModelSerializer):

    class Meta:
        model = ClientProject
        # Excluímos os campos de relacionamento que serão tratados em outras views
        fields = "__all__"
        
    def validate_tipoDocumento(self, value):
        if value and value.lower() not in ['cpf', 'cnpj']:
            raise serializers.ValidationError("Tipo de documento deve ser 'cpf' ou 'cnpj'.")
        return value

    def validate(self, data):
        tipo_documento = data.get('tipoDocumento', '').lower()
        documento = data.get('client_document') # Assumindo que o campo do modelo é 'client_document'

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
        validated_data['created_by'] = self.context['request'].user
        project = ClientProject.objects.create(**validated_data)
        return project

    def update(self, instance, validated_data):
        validated_data.pop('tipoDocumento', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

# Serializer para Listagem de Projetos (mantido como está, pois já é para listagem)
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

