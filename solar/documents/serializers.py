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

class DocumentUploadSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ProjectDocument
        fields = "__all__"
        read_only_fields = ['created_at', 'updated_at', 'approved_at']

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
            return data

        project = self.context.get('project') or (self.instance.project if self.instance else None)
        document_type = data.get('document_type') or (self.instance.document_type if self.instance else None)

        if not project:
            raise serializers.ValidationError("Projeto não identificado no contexto.")

        if document_type == 'comprovante_de_pagamento':
            related_payment = data.get('related_payment_document')
            
            if not related_payment:
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

        admin_only_docs = [
            'boleto', 'formulario', 'diagrama_unifilar', 
            'dados_geradora', 'unidades_consumidoras_extra', 
            'memorial', 'art_documento'
        ]

        energisa_only_docs = [
            'documento_de_posse'
        ]

        if document_type in energisa_only_docs:
            # O hasattr verifica se a tabela filha "EnergisaProject" está ligada a este projeto
            if not hasattr(project, 'energisaproject'):
                raise serializers.ValidationError({
                    'document_type': f"Acesso negado. O documento '{document_type}' é exclusivo para projetos do grupo Energisa."
                })
    
        if document_type in admin_only_docs:
            user = request.user
            if not (getattr(user, 'is_admin', False) or getattr(user, 'is_superuser', False)):
                raise serializers.ValidationError({
                    'document_type': f"Acesso negado. Apenas administradores podem enviar documentos do tipo: {document_type}."
                })
        return data

class PaymentDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDocument
        fields = '__all__'
        read_only_fields = ['status']

    def validate(self, data):
        user = self.context['request'].user
        if user.is_authenticated and user.is_cliente:
            if self.instance and self.instance.document_type == 'boleto':
                raise serializers.ValidationError("Clientes não podem editar boletos.")
        return data


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
    class Meta:
        model = ClientProject
        fields = '__all__'


class EnergisaProjectSerializer(AbstractProjectSerializer):
    class Meta:
        model = EnergisaProject
        fields = '__all__'


class ClientProjectUnifiedSerializer(EnergisaProjectSerializer):
    """
    O MAESTRO (Polimorfismo e MTI Protegida):
    Garante suporte unificado para criação e atualização de projetos Coelba e Energisa,
    com transações atômicas e proteção contra sobrescrita de snapshots na MTI do Django.
    """
    grupo = serializers.CharField(
        required=False, 
        default='coelba',
        help_text="Defina se o projeto é Coelba ou Energisa."
    )

    CAMPOS_ENERGISA = [
        'cabo_mm2', 'isolacao_volts', 'cabos_por_fase', 
        'disjuntor_amperes', 'dps_ka', 'dps_isolacao', 
        'tipo_ramal', 'tensao_tipo', 'tensao_imagem'
    ]

    class Meta(EnergisaProjectSerializer.Meta):
        model = EnergisaProject
        extra_kwargs = {
            'cabo_mm2': {'required': False, 'allow_null': True},
            'isolacao_volts': {'required': False, 'allow_null': True},
            'cabos_por_fase': {'required': False, 'allow_null': True},
            'disjuntor_amperes': {'required': False, 'allow_null': True},
            'dps_ka': {'required': False, 'allow_null': True},
            'dps_isolacao': {'required': False, 'allow_null': True},
            'tipo_ramal': {'required': False, 'allow_null': True},
            'tensao_tipo': {'required': False, 'allow_null': True},
            'tensao_imagem': {'required': False, 'allow_null': True},
        }

    def validate(self, data):
        # 1. Executa as validações base da classe abstrata (CPF, CNPJ, coordenadas)
        data = super().validate(data)
        
        grupo = data.get('grupo', getattr(self.instance, 'grupo', 'coelba'))

        if grupo == 'energisa':
            # Preenche valores padrão nos campos obrigatórios caso não venham no formulário
            data.setdefault('cabo_mm2', 10.0)
            data.setdefault('isolacao_volts', 750)
            data.setdefault('cabos_por_fase', 1)
            data.setdefault('disjuntor_amperes', 40.0)
            data.setdefault('dps_ka', 20.0)
            data.setdefault('tipo_ramal', 'aereo')
            data.setdefault('tensao_tipo', 'individual')
        else:
            # Se for Coelba, remove os campos exclusivos da Energisa para não dar erro na query do pai
            for campo in self.CAMPOS_ENERGISA:
                data.pop(campo, None)

        return data

    @transaction.atomic
    def create(self, validated_data):
        """
        CRIAÇÃO ATÔMICA:
        Cria o projeto dentro de um bloco atômico. Se marcado como 'energisa',
        o ORM do Django insere a linha na tabela pai e na tabela filha em uma única transação.
        """
        grupo = validated_data.get('grupo', 'coelba') 
        if grupo == 'energisa':
            # O ORM grava automaticamente em ClientProject e EnergisaProject
            return EnergisaProject.objects.create(**validated_data)
            
        # Projeto Coelba tradicional
        return ClientProject.objects.create(**validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        ATUALIZAÇÃO ATÔMICA E PROTEGIDA:
        Cobre os 3 cenários de atualização garantindo integridade no banco de dados.
        """
        novo_grupo = validated_data.get('grupo', instance.grupo)

        # ---------------------------------------------------------------------
        # CASO 1: Transição de Coelba -> Energisa (Criando o registro filho)
        # ---------------------------------------------------------------------
        if novo_grupo == 'energisa' and not hasattr(instance, 'energisaproject'):
            # Separa os dados específicos da Energisa
            energisa_data = {
                c: validated_data.pop(c) for c in self.CAMPOS_ENERGISA if c in validated_data
            }
            
            # Atualiza o modelo Pai (ClientProject)
            instance = super().update(instance, validated_data)

            # Insere o registro na tabela filha (documents_energisaproject) apontando para o pai
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO documents_energisaproject "
                    "(clientproject_ptr_id, cabo_mm2, isolacao_volts, cabos_por_fase, "
                    "disjuntor_amperes, dps_ka, dps_isolacao, tipo_ramal, tensao_tipo, tensao_imagem) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        instance.id,
                        energisa_data.get('cabo_mm2', 10.0),
                        energisa_data.get('isolacao_volts', 750),
                        energisa_data.get('cabos_por_fase', 1),
                        energisa_data.get('disjuntor_amperes', 40.0),
                        energisa_data.get('dps_ka', 20.0),
                        energisa_data.get('dps_isolacao', None),
                        energisa_data.get('tipo_ramal', 'aereo'),
                        energisa_data.get('tensao_tipo', 'individual'),
                        ''
                    ]
                )
            
            # Recarrega a instância completa sincronizando a memória Python com o banco
            return ClientProject.objects.select_related('energisaproject').get(pk=instance.pk)

        # ---------------------------------------------------------------------
        # CASO 2: Atualização de um projeto que JÁ É Energisa
        # ---------------------------------------------------------------------
        if novo_grupo == 'energisa' and hasattr(instance, 'energisaproject'):
            energisa_instance = instance.energisaproject
            
            # 1. Isola apenas os campos da Energisa que foram efetivamente alterados
            changed_fields = [attr for attr in self.CAMPOS_ENERGISA if attr in validated_data]
            for attr in changed_fields:
                setattr(energisa_instance, attr, validated_data.pop(attr))

            # 2. Atualiza a tabela PAI (ClientProject) para persistir status, nome, etc.
            instance = super().update(instance, validated_data)

            # 3. Atualiza a tabela FILHA (EnergisaProject) LIMITANDO aos seus próprios campos
            # (O update_fields é a chave: impede que o Django dispare UPDATE no pai com dados antigos)
            if changed_fields:
                energisa_instance.save(update_fields=changed_fields)

            # 4. Recarrega o projeto do banco de dados para a resposta JSON conter o status atualizado
            return ClientProject.objects.select_related('energisaproject').get(pk=instance.pk)

        # ---------------------------------------------------------------------
        # CASO 3: Atualização de projeto Coelba (ou retorno de Energisa para Coelba)
        # ---------------------------------------------------------------------
        for campo in self.CAMPOS_ENERGISA:
            validated_data.pop(campo, None)

        instance = super().update(instance, validated_data)
        return instance

    def to_representation(self, instance):
        # A serialização baseia-se na propriedade de grupo e na existência da relação filha
        grupo = getattr(instance, 'grupo', 'coelba')

        if grupo == 'energisa' and hasattr(instance, 'energisaproject'):
            data = EnergisaProjectSerializer(context=self.context).to_representation(instance.energisaproject)
            data['grupo'] = 'energisa'
            return data
            
        data = CoelbaProjectSerializer(context=self.context).to_representation(instance)
        data['grupo'] = 'coelba'
        return data

    def validate_grupo(self, value):
        if value:
            value = value.lower()
            opcoes_validas = ['energisa', 'coelba']
            if value not in opcoes_validas:
                raise serializers.ValidationError(f"Faça uma escolha válida. Aceitos: {', '.join(opcoes_validas)}")
        return value
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