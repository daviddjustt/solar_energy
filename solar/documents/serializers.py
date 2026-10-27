import re
from unicodedata import decimal
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import transaction, connection

from .models import ClientProject, ConsumerUnit, ProjectDocument, ListaDeMateriais, ProjectStatusHistory, ProjectProtocol, EnergisaProject
from .utils import VOLTAGEM_MAP, VOLTAGEM_CHOICES
from solar.files.utils import DOCUMENT_TYPE_CHOICES

# =========================================================================
# 1. HELPERS E CAMPOS CUSTOMIZADOS
# =========================================================================

class ProjectStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectStatusHistory
        fields = ['id', 'project', 'changed_by_uuid', 'old_status', 'new_status', 'changed_at']
        read_only_fields = fields 

class ProjectProtocolSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectProtocol
        fields = ['id', 'project', 'numero_protocolo', 'data_limite', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class VoltageField(serializers.CharField):
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


# =========================================================================
# 2. SERIALIZERS DE APOIO (Listas, Documentos, etc.)
# =========================================================================

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

class AbstractDocumentUploadSerializer(serializers.ModelSerializer):
    """
    Serializer Abstrato Base para qualquer modelo herdado de AbstractDocument.
    """
    download_url = serializers.SerializerMethodField()

    class Meta:
        abstract = True
        fields = [
            'id', 'document_name', 'document_type', 'status',
            'rejection_reason', 'approved_at', 'related_payment_document',
            'arquivo', 'download_url', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'approved_at']

    @extend_schema_field(OpenApiTypes.STR)
    def get_download_url(self, obj):
        request = self.context.get('request')
        download_endpoint_name = getattr(self.Meta, 'download_endpoint_name', None)
        parent_lookup_field = getattr(self.Meta, 'parent_lookup_field', 'project_id')
        
        if request and getattr(obj, parent_lookup_field, None) and obj.id and download_endpoint_name:
            parent_id = getattr(obj, parent_lookup_field)
            # Constrói a URL dinamicamente via reverse do DRF
            from django.urls import reverse
            try:
                path = reverse(download_endpoint_name, kwargs={'parent_pk': parent_id, 'document_pk': obj.id})
                return request.build_absolute_uri(path)
            except Exception:
                return None
        return None

    def validate(self, data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return data

        parent = self.context.get('parent') or getattr(self.instance, 'parent', None)
        document_type = data.get('document_type') or (self.instance.document_type if self.instance else None)

        # Validação financeira base de comprovantes
        if document_type == 'comprovante_de_pagamento':
            related_payment = data.get('related_payment_document')
            if related_payment and related_payment.document_type != 'boleto':
                raise serializers.ValidationError(
                    {'related_payment_document': 'O documento relacionado deve ser do tipo boleto.'}
                )

        return data

class AbstractPaymentDocumentSerializer(serializers.ModelSerializer):
    """
    Serializer Abstrato para gestão de Boletos e Comprovantes.
    """
    class Meta:
        abstract = True
        fields = ['id', 'document_type', 'status', 'rejection_reason', 'related_payment_document', 'arquivo']
        read_only_fields = ['status']

class DocumentUploadSerializer(AbstractDocumentUploadSerializer):
    project = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta(AbstractDocumentUploadSerializer.Meta):
        model = ProjectDocument
        fields = AbstractDocumentUploadSerializer.Meta.fields + ['project']
        download_endpoint_name = 'api:project-document-download'
        parent_lookup_field = 'project_id'


class PaymentDocumentSerializer(AbstractPaymentDocumentSerializer):
    class Meta(AbstractPaymentDocumentSerializer.Meta):
        model = ProjectDocument
        
# =========================================================================
# 3. ARQUITETURA POLIMÓRFICA DE PROJETOS (A Magia Acontece Aqui)
# =========================================================================

class AbstractProjectSerializer(serializers.ModelSerializer):
    """
    CLASSE ABSTRATA: Contém todo o comportamento padrão.
    Resolve redundância em todos os serializers de projetos.
    """
    voltagem = VoltageField()
    voltagem_label = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    
    documents = DocumentUploadSerializer(many=True, read_only=True)
    lista_materiais = ListaDeMateriaisSerializer(source='material_lists', many=True, read_only=True)
    consumer_units = ConsumerUnitSerializer(many=True, read_only=True)

    class Meta:
        abstract = True

    @extend_schema_field(OpenApiTypes.STR)
    def get_voltagem_label(self, obj):
        return obj.voltagem

    def validate(self, data):
        self.validate_coordinates(data)
        self.validate_cpf_cnpj(data)
        return data

    def to_internal_value(self, data):
        """
        Interceta os dados brutos ANTES da validação de tipos do DRF,
        permitindo tratar vírgulas e strings nas coordenadas.
        """
        if hasattr(data, '_mutable'):
            data = data.copy()
        elif isinstance(data, dict):
            data = data.copy()

        # Normaliza campos de coordenadas (substitui vírgula por ponto e converte)
        coord_fields_decimal = ['latSeg','longSeg']
        coord_fields_int = ['latMin', 'latGraus', 'longMin', 'longGraus']

        for field in coord_fields_decimal:
            if field in data and data[field] is not None:
                val = data[field]
                if isinstance(val, str):
                    val_cleaned = val.strip().replace(',', '.')
                    try:
                        data[field] = float(val_cleaned) if '.' in val_cleaned else int(val_cleaned)
                    except (ValueError, TypeError):
                        pass

        for field in coord_fields_int:
            if field in data and data[field] is not None:
                val = data[field]
                if isinstance(val, str):
                    val_cleaned = val.strip().replace(',', '.')
                    try:
                        data[field] = int(float(val_cleaned))
                    except (ValueError, TypeError):
                        pass

        return super().to_internal_value(data)

    def validate_coordinates(self, data):
        lat_graus = data.get('latGraus')
        long_graus = data.get('longGraus')

        if lat_graus is not None:
            if not (-90 <= float(lat_graus) <= 90):
                raise serializers.ValidationError({'latGraus': 'A latitude deve estar entre -90 e 90.'})
        if long_graus is not None:
            if not (-180 <= float(long_graus) <= 180):
                raise serializers.ValidationError({'longGraus': 'A longitude deve estar entre -180 e 180.'})

    def validate_cpf_cnpj(self, data):
        doc_type = data.get('tipoDocumento', '').upper()
        doc_val = data.get('documento')

        if doc_val:
            if doc_type == 'PF' and not re.match(r'^\d{3}\.\d{3}\.\d{3}-\d{2}$', doc_val):
                raise serializers.ValidationError({'documento': 'CPF inválido (000.000.000-00).'})
            if doc_type == 'PJ' and not re.match(r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$', doc_val):
                raise serializers.ValidationError({'documento': 'CNPJ inválido (00.000.000/0000-00).'})

class CoelbaProjectSerializer(AbstractProjectSerializer):
    """
    Serializer exclusivo para projetos da Coelba.
    Atua apenas na tabela pai (ClientProject).
    """
    grupo = serializers.CharField(required=False, default='coelba')

    class Meta:
        model = ClientProject
        fields = '__all__'
        
    def create(self, validated_data):
        validated_data['grupo'] = 'coelba'
        return super().create(validated_data)
        
    def update(self, instance, validated_data):
        validated_data['grupo'] = 'coelba'
        return super().update(instance, validated_data)

class EnergisaProjectSerializer(AbstractProjectSerializer):
    """
    Serializer exclusivo para projetos da Energisa.
    Lida com a tabela filha e com a transição segura (Coelba -> Energisa).
    """
    grupo = serializers.CharField(required=False, default='energisa')

    class Meta:
        model = EnergisaProject
        fields = '__all__'

    def create(self, validated_data):
        validated_data['grupo'] = 'energisa'
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data['grupo'] = 'energisa'
        
        # ---------------------------------------------------------------------
        # TRANSIÇÃO MTI: Se a instância recebida for estritamente um ClientProject
        # (classe pai), trata-se de um projeto Coelba a ser promovido a Energisa.
        # ---------------------------------------------------------------------

        if type(instance) is ClientProject:
            # 1. Isola os campos específicos da tabela filha
            cabo_mm2 = validated_data.pop('cabo_mm2', 10.0)
            isolacao_volts = validated_data.pop('isolacao_volts', 750)
            cabos_por_fase = validated_data.pop('cabos_por_fase', 1)
            disjuntor_amperes = validated_data.pop('disjuntor_amperes', 40.0)
            dps_ka = validated_data.pop('dps_ka', 20.0)
            dps_isolacao = validated_data.pop('dps_isolacao', None)
            tipo_ramal = validated_data.pop('tipo_ramal', 'aereo')
            tensao_tipo = validated_data.pop('tensao_tipo', 'individual')
            
            # RETIRAMOS o arquivo da payload para não quebrar o RAW SQL
            tensao_imagem = validated_data.pop('tensao_imagem', None)
            
            # 2. Atualiza os dados comuns na tabela pai
            instance = super().update(instance, validated_data)
            
            # 3. Cria o vínculo na tabela filha forçando SQL puro
            # Passamos '' (string vazia) no lugar da imagem
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO documents_energisaproject "
                    "(clientproject_ptr_id, cabo_mm2, isolacao_volts, cabos_por_fase, "
                    "disjuntor_amperes, dps_ka, dps_isolacao, tipo_ramal, tensao_tipo, tensao_imagem) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        instance.id, cabo_mm2, isolacao_volts, cabos_por_fase, 
                        disjuntor_amperes, dps_ka, dps_isolacao, tipo_ramal, tensao_tipo, ''
                    ]
                )
                
            # 4. Recupera a instância já promovida
            promoted_instance = EnergisaProject.objects.get(pk=instance.id)
            
            # 5. Se houver imagem, salva usando o ORM do Django (que processa o upload físico do arquivo)
            if tensao_imagem:
                promoted_instance.tensao_imagem = tensao_imagem
                promoted_instance.save(update_fields=['tensao_imagem'])
                
            # Retorna a instância completa promovida
            return promoted_instance

        # Se já for EnergisaProject (atualização padrão), o DRF faz o update MTI nativo
        return super().update(instance, validated_data)
# =========================================================================
# 4. SERIALIZERS DE LEITURA E ATUALIZAÇÃO (Herdam de Abstract)
# =========================================================================

class ProjectInfoSerializer(AbstractProjectSerializer):
    class Meta:
        model = ClientProject
        fields = "__all__"
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'valor_total', 'resumo_financeiro')

class ProjectListSerializer(AbstractProjectSerializer):
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

class TecnicoClientProjectSerializer(AbstractProjectSerializer):
    class Meta:
        model = ClientProject
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'tipo_financeiro', 'valor_financeiro', 'parcelas')

class ClientProjectSerializer(AbstractProjectSerializer):
    class Meta:
        model = ClientProject
        fields = '__all__'

class ClientProjectUpdateSerializer(AbstractProjectSerializer):
    class Meta:
        model = ClientProject
        fields = '__all__'
        read_only_fields = (
            'id', 'created_at', 'created_by', 'codigoCliente', 
            'documents', 'consumer_units', 'material_lists'
        )