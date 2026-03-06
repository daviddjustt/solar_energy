import re
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from .models import ClientProject, ConsumerUnit, ProjectDocument, ListaDeMateriais
from .utils import VOLTAGEM_MAP, VOLTAGEM_CHOICES
from solar.files.utils import DOCUMENT_TYPE_CHOICES

# --- Helpers e Campos Customizados ---

class VoltageField(serializers.CharField):
    """Campo que aceita valores curtos (127) e salva o label completo."""
    def to_internal_value(self, data):
        if not data:
            raise serializers.ValidationError("Voltagem é obrigatória")
        
        value_str = str(data).strip()
        converted_label = VOLTAGEM_MAP.get(value_str)
        
        if converted_label:
            return converted_label
            
        valid_model_choices = [choice[0] for choice in VOLTAGEM_CHOICES]
        if value_str in valid_model_choices:
            return value_str

        raise serializers.ValidationError(f"Voltagem inválida. Aceitos: {', '.join(VOLTAGEM_MAP.keys())}")

# --- Serializers de Apoio ---

class ConsumerUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumerUnit
        fields = "__all__"
        read_only_fields = ['project']
    
    def validate(self, data):
        is_pct = data.get('prioridade_is_porcentagem')
        pct = data.get('porcentagem')
        lvl = data.get('priority_level')

        if is_pct is True:
            if pct in [None, '']:
                raise serializers.ValidationError({'porcentagem': 'Obrigatório quando prioridade_is_porcentagem é True.'})
            if lvl not in [None, '']:
                raise serializers.ValidationError({'priority_level': 'Deve ser vazio quando prioridade_is_porcentagem é True.'})
        elif is_pct is False:
            if lvl in [None, '']:
                raise serializers.ValidationError({'priority_level': 'Obrigatório quando prioridade_is_porcentagem é False.'})
            if pct not in [None, '']:
                raise serializers.ValidationError({'porcentagem': 'Deve ser vazio quando prioridade_is_porcentagem é False.'})
        return data

class ListaDeMateriaisSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaDeMateriais
        fields = "__all__"
        read_only_fields = ['project']

# --- Serializer de Documentos (Upload) ---

class DocumentUploadSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ProjectDocument
        fields = "__all__"
        read_only_fields = ['created_at', 'updated_at', 'approved_at', 'status']

    @extend_schema_field(OpenApiTypes.STR)
    def get_download_url(self, obj):
        request = self.context.get('request')
        if request and obj.project_id and obj.id:
            return request.build_absolute_uri(
                f'/api/v1/projects/{obj.project_id}/documents/{obj.id}/download/'
            )
        return None

    def validate(self, data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            # Proteção crucial para o Swagger não quebrar ao tentar validar sem usuário
            return data

        user = request.user
        project = self.context.get('project') or (self.instance.project if self.instance else None)
        document_type = data.get('document_type') or (self.instance.document_type if self.instance else None)

        if not project:
            raise serializers.ValidationError("Projeto não identificado no contexto.")

        # Validação de Comprovante x Boleto
        if document_type == 'comprovante_de_pagamento':
            related_payment = data.get('related_payment_document')
            
            if not related_payment:
                # Verifica se existe algum boleto no projeto
                has_boleto = ProjectDocument.objects.filter(project=project, document_type='boleto').exists()
                if not has_boleto:
                    raise serializers.ValidationError({'related_payment_document': 'Crie um boleto antes de enviar o comprovante.'})
                
                if request.method != 'PATCH':
                    raise serializers.ValidationError({'related_payment_document': 'Este campo é obrigatório para comprovantes.'})

            if related_payment:
                if related_payment.document_type != 'boleto':
                    raise serializers.ValidationError({'related_payment_document': 'O documento relacionado deve ser do tipo boleto.'})
                if related_payment.project_id != project.id:
                    raise serializers.ValidationError({'related_payment_document': 'O boleto deve pertencer ao mesmo projeto.'})

        return data

# --- Serializers de Projeto (Base e Especializados) ---

class ProjectBaseSerializer(serializers.ModelSerializer):
    """Classe base para evitar repetição de lógica entre Info, List e Tecnico"""
    voltagem = VoltageField()
    voltagem_label = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)

    @extend_schema_field(OpenApiTypes.STR)
    def get_voltagem_label(self, obj):
        return obj.voltagem

    def validate_coordinates(self, data):
        """Valida grupos de latitude e longitude"""
        lat_group = [data.get('lat_degrees'), data.get('lat_minutes'), data.get('lat_seconds')]
        long_group = [data.get('long_degrees'), data.get('long_minutes'), data.get('long_seconds')]

        if any(x is not None for x in lat_group) and not all(x is not None for x in lat_group):
            raise serializers.ValidationError("Preencha todos os campos de latitude (graus, min, seg).")
        if any(x is not None for x in long_group) and not all(x is not None for x in long_group):
            raise serializers.ValidationError("Preencha todos os campos de longitude (graus, min, seg).")

    def validate_cpf_cnpj(self, data):
        """Validação de formato de documento de cliente"""
        doc_type = data.get('tipoDocumento', '').upper()
        doc_val = data.get('client_document')

        if doc_val:
            if doc_type == 'PF' and not re.match(r'^\d{3}\.\d{3}\.\d{3}-\d{2}$', doc_val):
                raise serializers.ValidationError({'client_document': 'CPF inválido (000.000.000-00).'})
            if doc_type == 'PJ' and not re.match(r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$', doc_val):
                raise serializers.ValidationError({'client_document': 'CNPJ inválido (00.000.000/0000-00).'})

class ProjectInfoSerializer(ProjectBaseSerializer):
    # Usamos o SerializerMethodField para garantir que o retorno seja SEMPRE uma lista
    documents = serializers.SerializerMethodField()
    lista_materiais = serializers.SerializerMethodField()

    class Meta:
        model = ClientProject
        fields = "__all__"
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'valor_total', 'resumo_financeiro')

    @extend_schema_field(DocumentUploadSerializer(many=True))
    def get_documents(self, obj):
        # Busca os documentos relacionados. Tente 'documents' ou 'projectdocument_set'
        # O .all() aqui garante que retornamos um QuerySet que o Serializer converte em LISTA []
        docs = obj.documents.all() 
        return DocumentUploadSerializer(docs, many=True, context=self.context).data

    @extend_schema_field(ListaDeMateriaisSerializer(many=True))
    def get_lista_materiais(self, obj):
        materiais = obj.lista_materiais.all()
        return ListaDeMateriaisSerializer(materiais, many=True, context=self.context).data

class ProjectListSerializer(ProjectBaseSerializer):
    tipoDocumento_label = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()
    consumer_units_count = serializers.SerializerMethodField()

    class Meta:
        model = ClientProject
        fields = "__all__"
        read_only_fields = ('created_by', 'created_at', 'updated_at')

    @extend_schema_field(OpenApiTypes.STR)
    def get_tipoDocumento_label(self, obj):
        return "Pessoa Física" if obj.tipoDocumento == 'PF' else "Pessoa Jurídica"

    @extend_schema_field(OpenApiTypes.INT)
    def get_documents_count(self, obj):
        return obj.documents.count()

    @extend_schema_field(OpenApiTypes.INT)
    def get_consumer_units_count(self, obj):
        return obj.consumer_units.count()

class TecnicoClientProjectSerializer(ProjectBaseSerializer):
    """Garante que o Técnico também veja a lista de documentos/materiais sem quebrar o Front"""
    documents = DocumentUploadSerializer(many=True, read_only=True)
    lista_materiais = ListaDeMateriaisSerializer(many=True, read_only=True)
    consumer_units = ConsumerUnitSerializer(many=True, read_only=True)

    class Meta:
        model = ClientProject
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'tipo_financeiro', 'valor_financeiro', 'parcelas')

class PaymentDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDocument
        fields = '__all__'
        read_only_fields = ['status']

    def validate(self, data):
        user = self.context['request'].user
        if user.is_authenticated and user.is_cliente:
            # Cliente tentando editar boleto
            if self.instance and self.instance.document_type == 'boleto':
                raise serializers.ValidationError("Clientes não podem editar boletos.")
        return data