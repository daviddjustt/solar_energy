from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# Local Apps - Models
from arcanosig.oper.models.cautela import (
    CautelaIndividual,
    ItemCautela,
    AceiteCautela,
    TipoEquipamento,
    StatusEquipamento,
    StatusAceite,
)

# Local Apps - Serializers
from arcanosig.oper.serializers.base_serializers import BaseModelSerializer
from arcanosig.users.serializers import UserSerializer



# ITEM CAUTELA SERIALIZERS


class ItemCautelaSerializer(BaseModelSerializer):
    """Serializer completo para o modelo ItemCautela."""
    
    tipo_equipamento_display = serializers.CharField(
        source='get_tipo_equipamento_display', 
        read_only=True
    )
    status_equipamento_display = serializers.CharField(
        source='get_status_equipamento_display', 
        read_only=True
    )

    class Meta:
        model = ItemCautela
        fields = [
            'id', 'cautela', 'tipo_equipamento', 'tipo_equipamento_display',
            'numero_serie', 'quantidade', 'data_devolucao', 'status_equipamento',
            'status_equipamento_display', 'descricao_danos', 'devolucao_confirmada',
            'protocolo_devolucao', 'observacao', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'tipo_equipamento_display',
            'status_equipamento_display', 'protocolo_devolucao', 'data_devolucao'
        ]

    def validate(self, data):
        """Validações adicionais para itens de cautela."""
        instance = ItemCautela(**data)
        if self.instance:
            for attr, value in data.items():
                setattr(self.instance, attr, value)
            instance = self.instance
        instance.clean()
        return data


class ItemCautelaNestedSerializer(BaseModelSerializer):
    """Serializer para ItemCautela usado em relacionamentos aninhados."""
    
    tipo_equipamento_display = serializers.CharField(
        source='get_tipo_equipamento_display', 
        read_only=True
    )
    status_equipamento_display = serializers.CharField(
        source='get_status_equipamento_display', 
        read_only=True
    )

    class Meta:
        model = ItemCautela
        fields = [
            'id', 'tipo_equipamento', 'tipo_equipamento_display',
            'numero_serie', 'quantidade', 'data_devolucao',
            'status_equipamento', 'status_equipamento_display',
            'descricao_danos', 'devolucao_confirmada',
            'protocolo_devolucao'
        ]
        read_only_fields = fields



# ACEITE CAUTELA SERIALIZERS


class AceiteCautelaSerializer(BaseModelSerializer):
    """Serializer completo para o modelo AceiteCautela."""
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = AceiteCautela
        fields = [
            'id', 'cautela', 'protocolo', 'status', 'status_display',
            'data_aceite', 'ip_aceite', 'observacao', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'protocolo', 'data_aceite',
            'ip_aceite', 'status_display'
        ]

    def validate(self, data):
        """Validações adicionais para aceites de cautela."""
        instance = AceiteCautela(**data)
        if self.instance:
            for attr, value in data.items():
                setattr(self.instance, attr, value)
            instance = self.instance
        instance.clean()
        return data


class AceiteCautelaNestedSerializer(BaseModelSerializer):
    """Serializer para AceiteCautela usado em relacionamentos aninhados."""
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = AceiteCautela
        fields = [
            'id', 'protocolo', 'status', 'status_display',
            'data_aceite', 'observacao', 'created_at'
        ]
        read_only_fields = fields


class AceiteCautelaConfirmacaoSerializer(serializers.Serializer):
    """Serializer para confirmar aceite de cautela."""
    
    observacao = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        """Validação básica dos dados de confirmação."""
        return data



# CAUTELA INDIVIDUAL SERIALIZERS


class CautelaIndividualSerializer(BaseModelSerializer):
    """Serializer completo para o modelo CautelaIndividual."""
    
    # Relacionamentos
    policial = UserSerializer(read_only=True)
    policial_id = serializers.UUIDField(write_only=True)
    itens = ItemCautelaNestedSerializer(many=True, read_only=True)
    aceites = serializers.SerializerMethodField()
    
    # Campos calculados
    status_text = serializers.CharField(source='status', read_only=True)
    
    # Dados da guarnição
    guarnicao_nome = serializers.CharField(source='guarnicao.name', read_only=True)
    id_guarnicao = serializers.UUIDField(source='guarnicao.id', read_only=True)
    
    # Dados da operação
    nome_operacao = serializers.CharField(source='guarnicao.operacao.name', read_only=True)
    id_operacao = serializers.UUIDField(source='guarnicao.operacao.id', read_only=True)

    class Meta:
        model = CautelaIndividual
        fields = [
            'id', 'policial', 'policial_id', 'guarnicao', 'guarnicao_nome', 'id_guarnicao',
            'data_entrega', 'data_devolucao', 'observacao_devolucao', 'aceite_status',
            'protocolo_aceite', 'data_hora_aceite', 'aceites', 'itens', 'status_text',
            'created_at', 'updated_at', 'nome_operacao', 'id_operacao'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'aceite_status', 'protocolo_aceite',
            'data_hora_aceite', 'status_text', 'guarnicao_nome', 'id_guarnicao',
            'nome_operacao', 'id_operacao'
        ]

    def get_aceites(self, obj):
        """Retorna os aceites associados à cautela ordenados por data."""
        if not hasattr(obj, 'historico_aceites'):
            return []
        
        aceites = obj.historico_aceites.all().order_by('-created_at')
        return AceiteCautelaNestedSerializer(aceites, many=True).data

    def validate(self, data):
        """Validações adicionais para cautelas."""
        instance = CautelaIndividual(**data)
        if self.instance:
            for attr, value in data.items():
                setattr(self.instance, attr, value)
            instance = self.instance
        instance.clean()
        return data


class CautelaIndividualListSerializer(BaseModelSerializer):
    """Serializer simplificado para listagem de cautelas."""
    
    # Dados do policial
    policial_nome = serializers.CharField(source='policial.name', read_only=True)
    policial_patente = serializers.CharField(source='policial.get_patent_display', read_only=True)
    
    # Dados da guarnição
    guarnicao_nome = serializers.CharField(source='guarnicao.name', read_only=True)
    
    # Campos calculados
    itens_count = serializers.SerializerMethodField()
    status_text = serializers.CharField(source='status', read_only=True)
    operacoes_ids = serializers.SerializerMethodField()

    class Meta:
        model = CautelaIndividual
        fields = [
            'id', 'policial_nome', 'policial_patente', 'guarnicao_nome',
            'data_entrega', 'data_devolucao', 'itens_count',
            'aceite_status', 'status_text', 'operacoes_ids'
        ]
        read_only_fields = fields

    def get_itens_count(self, obj):
        """Retorna o número de itens na cautela."""
        return obj.itens.count()

    def get_operacoes_ids(self, obj):
        """Retorna os IDs das operações relacionadas através da guarnição."""
        if (obj.guarnicao and 
            hasattr(obj.guarnicao, 'operacao') and 
            obj.guarnicao.operacao):
            return [obj.guarnicao.operacao.id]
        return []



# DEVOLUÇÃO SERIALIZERS


class DevolucaoItemSerializer(serializers.Serializer):
    """Serializer para registrar devolução de item de cautela."""
    
    status_equipamento = serializers.ChoiceField(
        choices=StatusEquipamento.choices,
        default=StatusEquipamento.EM_CONDICOES
    )
    descricao_danos = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        """Valida se descrição de danos foi fornecida para equipamentos danificados."""
        status = data.get('status_equipamento')
        descricao = data.get('descricao_danos', '')

        # Verifica se a descrição dos danos foi fornecida para equipamentos danificados
        if status in [StatusEquipamento.DANIFICADO, StatusEquipamento.INOPERANTE] and not descricao:
            raise serializers.ValidationError(
                _("É necessário descrever os danos quando o equipamento está danificado ou inoperante.")
            )
        
        return data


class DevolucaoCautelaSerializer(serializers.Serializer):
    """Serializer para registrar devolução completa de cautela."""
    
    observacao = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        """Validação básica dos dados de devolução."""
        return data



# RELATÓRIO E ESTATÍSTICA SERIALIZERS


class CautelaResumoOperacaoSerializer(serializers.Serializer):
    """Serializer para resumo de operações de cautela com dados agregados."""
    
    id_operacao = serializers.UUIDField()
    nome_operacao = serializers.CharField()
    quantidade_equipamentos_danificados = serializers.IntegerField()
    quantidade_cautelas_ativas = serializers.IntegerField()
    quantidade_aceites_confirmados = serializers.IntegerField()
    quantidade_aceites_pendentes = serializers.IntegerField()

    def validate(self, data):
        """Validação dos dados do resumo."""
        # Verificar se os valores são não negativos
        for field in ['quantidade_equipamentos_danificados', 'quantidade_cautelas_ativas', 
                     'quantidade_aceites_confirmados', 'quantidade_aceites_pendentes']:
            if data.get(field, 0) < 0:
                raise serializers.ValidationError(
                    {field: _("O valor não pode ser negativo.")}
                )
        
        return data


class CautelaEstatisticasDetalhadas(serializers.Serializer):
    """Serializer para estatísticas detalhadas de cautelas."""
    
    # Totais gerais
    total_cautelas = serializers.IntegerField()
    cautelas_ativas = serializers.IntegerField()
    cautelas_devolvidas = serializers.IntegerField()
    
    # Estatísticas de aceite
    aceites_pendentes = serializers.IntegerField()
    aceites_confirmados = serializers.IntegerField()
    
    # Estatísticas de equipamentos
    total_equipamentos = serializers.IntegerField()
    equipamentos_em_condicoes = serializers.IntegerField()
    equipamentos_danificados = serializers.IntegerField()
    equipamentos_inoperantes = serializers.IntegerField()
    
    # Dados temporais
    periodo_inicio = serializers.DateTimeField()
    periodo_fim = serializers.DateTimeField()


class GuarnicaoEstatisticasSerializer(serializers.Serializer):
    """Serializer para estatísticas por guarnição."""
    
    id = serializers.UUIDField()
    name = serializers.CharField()
    total_cautelas = serializers.IntegerField()
    cautelas_ativas = serializers.IntegerField()
    itens_danificados = serializers.IntegerField()


class EquipamentoRankingSerializer(serializers.Serializer):
    """Serializer para ranking de equipamentos mais cautelados."""
    
    tipo_equipamento = serializers.CharField()
    quantidade = serializers.IntegerField()
    percentual = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)



# DASHBOARD SERIALIZERS


class DashboardCautelaSerializer(serializers.Serializer):
    """Serializer para dados do dashboard de cautelas."""
    
    # Resumo geral
    resumo_geral = CautelaEstatisticasDetalhadas()
    
    # Top guarnições
    top_guarnicoes = GuarnicaoEstatisticasSerializer(many=True)
    
    # Equipamentos mais cautelados
    equipamentos_ranking = EquipamentoRankingSerializer(many=True)
    
    # Alertas
    alertas_aceites_pendentes = serializers.IntegerField()
    alertas_equipamentos_danificados = serializers.IntegerField()
    
    # Timestamp
    timestamp = serializers.DateTimeField()


class CautelaMetricasSerializer(serializers.Serializer):
    """Serializer para métricas de performance de cautelas."""
    
    tempo_medio_aceite = serializers.DurationField()
    tempo_medio_devolucao = serializers.DurationField()
    taxa_danos_equipamentos = serializers.DecimalField(max_digits=5, decimal_places=2)
    taxa_aceite_pendente = serializers.DecimalField(max_digits=5, decimal_places=2)
    
    # Dados por período
    periodo = serializers.CharField()
    data_calculo = serializers.DateTimeField()
