from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import date, timedelta
from uuid import UUID

# Django Core
from django.db import transaction
from django.db.models import Count, Sum, Avg, Max, Min, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

# Django REST Framework
from rest_framework import serializers
from rest_framework.fields import (
    CharField, 
    UUIDField, 
    BooleanField, 
    DecimalField
)
# Local Apps
from arcanosig.oper.models.veiculo import (
    Veiculo,
    FotoVeiculo,
    Abastecimento,
    ModeloVeiculo
)
from arcanosig.oper.serializers.base_serializers import (
    BaseModelSerializer, 
    UserSerializer,
)

# BASIC SERIALIZERS


class ModeloVeiculoSerializer(BaseModelSerializer):
    """
    Serializer para modelos de veículos.
    
    Fornece informações básicas sobre os modelos disponíveis
    para seleção durante a criação de veículos.
    """
    
    class Meta:
        model = ModeloVeiculo
        fields = ['id', 'nome', 'fabricante', 'categoria', 'is_active']
        read_only_fields = fields


class VeiculoBasicSerializer(BaseModelSerializer):
    """
    Serializer básico para informações essenciais de veículos.
    
    Usado em contextos onde apenas informações básicas são necessárias,
    como em listagens de guarnições e seleções de veículos.
    """
    
    modelo_display = CharField(source='get_modelo_display', read_only=True)
    status_display = serializers.SerializerMethodField()
    autonomia_estimada = serializers.SerializerMethodField()
    
    class Meta:
        model = Veiculo
        fields = [
            'id', 'placa', 'modelo', 'modelo_display', 
            'em_condicao', 'status_display', 'km_atual',
            'autonomia_estimada'
        ]
        read_only_fields = fields
    
    def get_status_display(self, obj: Veiculo) -> str:
        """Retorna status legível do veículo."""
        if obj.em_condicao:
            return _("Operacional")
        return _("Manutenção")
    
    def get_autonomia_estimada(self, obj: Veiculo) -> Optional[str]:
        """Calcula autonomia estimada baseada no último abastecimento."""
        ultimo_abastecimento = obj.abastecimentos.order_by('-data').first()
        if ultimo_abastecimento and ultimo_abastecimento.litros > 0:
            # Estimativa simples baseada em 10km/l (pode ser configurável)
            autonomia_km = ultimo_abastecimento.litros * 10
            return f"{autonomia_km:.0f} km"
        return None


class FotoVeiculoBasicSerializer(BaseModelSerializer):
    """
    Serializer básico para fotos de veículos.
    
    Fornece informações essenciais sobre fotos sem carregar
    metadados desnecessários para listagens simples.
    """
    
    # Configurar campo de imagem conforme necessário
    # imagem = serializers.ImageField()
    # imagem_thumbnail = serializers.SerializerMethodField()
    
    veiculo_placa = CharField(source='veiculo.placa', read_only=True)
    tamanho_arquivo = serializers.SerializerMethodField()
    
    class Meta:
        model = FotoVeiculo
        fields = [
            'id', 'veiculo', 'veiculo_placa', 
            'created_at', 'tamanho_arquivo'
        ]
        read_only_fields = ['created_at', 'veiculo_placa', 'tamanho_arquivo']
    
    def get_tamanho_arquivo(self, obj: FotoVeiculo) -> Optional[str]:
        """Retorna tamanho do arquivo formatado."""
        # TODO: Implementar quando campo de imagem for configurado
        return None


class AbastecimentoBasicSerializer(BaseModelSerializer):
    """
    Serializer básico para registros de abastecimento.
    
    Usado em listagens e contextos onde apenas informações
    essenciais sobre abastecimentos são necessárias.
    """
    
    veiculo_placa = CharField(source='veiculo.placa', read_only=True)
    custo_por_litro = serializers.SerializerMethodField()
    tempo_desde_abastecimento = serializers.SerializerMethodField()
    
    class Meta:
        model = Abastecimento
        fields = [
            'id', 'veiculo', 'veiculo_placa', 'data',
            'km_atual', 'litros', 'valor_total',
            'custo_por_litro', 'tempo_desde_abastecimento'
        ]
        read_only_fields = [
            'veiculo_placa', 'custo_por_litro', 'tempo_desde_abastecimento'
        ]
    
    def get_custo_por_litro(self, obj: Abastecimento) -> Optional[Decimal]:
        """Calcula custo por litro."""
        if obj.litros and obj.litros > 0 and obj.valor_total:
            return round(obj.valor_total / obj.litros, 2)
        return None
    
    def get_tempo_desde_abastecimento(self, obj: Abastecimento) -> str:
        """Calcula tempo desde o abastecimento."""
        if not obj.data:
            return ""
        
        hoje = date.today()
        delta = hoje - obj.data
        
        if delta.days == 0:
            return _("Hoje")
        elif delta.days == 1:
            return _("Ontem")
        elif delta.days <= 7:
            return _("%(days)d dias atrás") % {'days': delta.days}
        elif delta.days <= 30:
            semanas = delta.days // 7
            return _("%(weeks)d semanas atrás") % {'weeks': semanas}
        else:
            meses = delta.days // 30
            return _("%(months)d meses atrás") % {'months': meses}



# LIST SERIALIZERS


class VeiculoListSerializer(BaseModelSerializer):
    """
    Serializer otimizado para listagem de veículos.
    
    Versão simplificada focada em performance para operações de listagem,
    incluindo informações essenciais e estatísticas básicas.
    """
    
    modelo_display = CharField(source='get_modelo_display', read_only=True)
    status_display = serializers.SerializerMethodField()
    guarnicao_atual = serializers.SerializerMethodField()
    ultimo_abastecimento = serializers.SerializerMethodField()
    
    class Meta:
        model = Veiculo
        fields = [
            'id', 'placa', 'modelo', 'modelo_display', 
            'em_condicao', 'status_display', 'km_atual',
            'guarnicao_atual', 'ultimo_abastecimento'
        ]
        read_only_fields = fields
    
    def get_status_display(self, obj: Veiculo) -> str:
        """Status simplificado do veículo."""
        if obj.em_condicao:
            return _("Operacional")
        return _("Manutenção")
    
    def get_guarnicao_atual(self, obj: Veiculo) -> Optional[Dict[str, Any]]:
        """Retorna guarnição atual se houver."""
        if hasattr(obj, 'guarnicao_associada') and obj.guarnicao_associada:
            return {
                'id': obj.guarnicao_associada.id,
                'nome': obj.guarnicao_associada.name
            }
        return None
    
    def get_ultimo_abastecimento(self, obj: Veiculo) -> Optional[str]:
        """Data do último abastecimento."""
        ultimo = obj.abastecimentos.order_by('-data').first()
        if ultimo:
            return ultimo.data.strftime('%d/%m/%Y')
        return None


class AbastecimentoListSerializer(BaseModelSerializer):
    """
    Serializer otimizado para listagem de abastecimentos.
    
    Versão simplificada para dashboards e relatórios básicos
    de consumo de combustível.
    """
    
    veiculo_placa = CharField(source='veiculo.placa', read_only=True)
    custo_por_litro = serializers.SerializerMethodField()
    consumo_medio = serializers.SerializerMethodField()
    
    class Meta:
        model = Abastecimento
        fields = [
            'id', 'veiculo_placa', 'data', 'km_atual', 
            'litros', 'valor_total', 'custo_por_litro', 'consumo_medio'
        ]
        read_only_fields = fields
    
    def get_custo_por_litro(self, obj: Abastecimento) -> Optional[Decimal]:
        """Calcula custo por litro."""
        if obj.litros and obj.litros > 0 and obj.valor_total:
            return round(obj.valor_total / obj.litros, 2)
        return None
    
    def get_consumo_medio(self, obj: Abastecimento) -> Optional[str]:
        """Calcula consumo médio desde último abastecimento."""
        abastecimento_anterior = obj.veiculo.abastecimentos.filter(
            data__lt=obj.data
        ).order_by('-data').first()
        
        if abastecimento_anterior:
            km_percorridos = obj.km_atual - abastecimento_anterior.km_atual
            if km_percorridos > 0 and obj.litros > 0:
                consumo = km_percorridos / obj.litros
                return f"{consumo:.1f} km/l"
        
        return None



# COMPLETE SERIALIZERS


class FotoVeiculoSerializer(BaseModelSerializer):
    """
    Serializer completo para o modelo FotoVeiculo.
    
    Permite o upload e gerenciamento completo de fotos de veículos,
    incluindo validações de formato e tamanho.
    """
    
    # Configurar campo de imagem conforme necessário
    # imagem = serializers.ImageField()
    # imagem_thumbnail = serializers.ImageField(read_only=True)
    
    
    # RELATIONSHIP FIELDS
    
    
    veiculo_placa = CharField(source='veiculo.placa', read_only=True)
    veiculo_modelo = CharField(source='veiculo.get_modelo_display', read_only=True)
    
    
    # COMPUTED FIELDS
    
    
    tamanho_arquivo = serializers.SerializerMethodField()
    formato_arquivo = serializers.SerializerMethodField()
    url_visualizacao = serializers.SerializerMethodField()
    
    class Meta:
        model = FotoVeiculo
        fields = [
            'id', 'veiculo', 'veiculo_placa', 'veiculo_modelo',
            'created_at', 'tamanho_arquivo', 'formato_arquivo',
            'url_visualizacao'
        ]
        read_only_fields = [
            'created_at', 'veiculo_placa', 'veiculo_modelo',
            'tamanho_arquivo', 'formato_arquivo', 'url_visualizacao'
        ]

    
    # SERIALIZER METHOD FIELDS
    
    
    def get_tamanho_arquivo(self, obj: FotoVeiculo) -> Optional[str]:
        """Retorna tamanho do arquivo formatado."""
        # TODO: Implementar quando campo de imagem for configurado
        # if obj.imagem:
        #     size = obj.imagem.size
        #     if size < 1024:
        #         return f"{size} bytes"
        #     elif size < 1024 * 1024:
        #         return f"{size / 1024:.1f} KB"
        #     else:
        #         return f"{size / (1024 * 1024):.1f} MB"
        return None
    
    def get_formato_arquivo(self, obj: FotoVeiculo) -> Optional[str]:
        """Retorna formato do arquivo."""
        # TODO: Implementar quando campo de imagem for configurado
        return None
    
    def get_url_visualizacao(self, obj: FotoVeiculo) -> Optional[str]:
        """Retorna URL para visualização da foto."""
        # TODO: Implementar quando campo de imagem for configurado
        return None

    
    # VALIDATION METHODS
    
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validações adicionais para fotos de veículos."""
        self._validate_veiculo_exists(data)
        # TODO: Adicionar validações de imagem quando campo for configurado
        # self._validate_image_format(data)
        # self._validate_image_size(data)
        
        # Aplica validações do modelo
        instance = FotoVeiculo(**data)
        if self.instance:
            for attr, value in data.items():
                setattr(self.instance, attr, value)
            instance = self.instance
        
        instance.clean()
        return data
    
    def _validate_veiculo_exists(self, data: Dict[str, Any]) -> None:
        """Valida se o veículo existe."""
        veiculo = data.get('veiculo')
        if veiculo and not Veiculo.objects.filter(id=veiculo.id).exists():
            raise serializers.ValidationError({
                'veiculo': _("Veículo não encontrado.")
            })


class AbastecimentoSerializer(BaseModelSerializer):
    """
    Serializer completo para o modelo Abastecimento.
    
    Gerencia registros completos de abastecimento incluindo
    validações de negócio e atualizações automáticas de quilometragem.
    """
    
    
    # RELATIONSHIP FIELDS
    
    
    veiculo_placa = CharField(source='veiculo.placa', read_only=True)
    veiculo_modelo = CharField(source='veiculo.get_modelo_display', read_only=True)
    
    
    # COMPUTED FIELDS
    
    
    custo_por_litro = serializers.SerializerMethodField()
    consumo_medio = serializers.SerializerMethodField()
    km_percorridos = serializers.SerializerMethodField()
    eficiencia = serializers.SerializerMethodField()
    
    
    # VALIDATION FIELDS
    
    
    diferenca_km = serializers.SerializerMethodField()
    alerta_consumo = serializers.SerializerMethodField()
    
    class Meta:
        model = Abastecimento
        fields = [
            'id', 'veiculo', 'veiculo_placa', 'veiculo_modelo',
            'data', 'km_atual', 'litros', 'valor_total', 'observacao',
            'custo_por_litro', 'consumo_medio', 'km_percorridos',
            'eficiencia', 'diferenca_km', 'alerta_consumo',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'veiculo_placa', 'veiculo_modelo',
            'custo_por_litro', 'consumo_medio', 'km_percorridos',
            'eficiencia', 'diferenca_km', 'alerta_consumo'
        ]

    
    # SERIALIZER METHOD FIELDS
    
    
    def get_custo_por_litro(self, obj: Abastecimento) -> Optional[Decimal]:
        """Calcula custo por litro."""
        if obj.litros and obj.litros > 0 and obj.valor_total:
            return round(obj.valor_total / obj.litros, 2)
        return None
    
    def get_consumo_medio(self, obj: Abastecimento) -> Optional[Dict[str, Any]]:
        """Calcula consumo médio detalhado."""
        abastecimento_anterior = obj.veiculo.abastecimentos.filter(
            data__lt=obj.data
        ).order_by('-data').first()
        
        if abastecimento_anterior:
            km_percorridos = obj.km_atual - abastecimento_anterior.km_atual
            if km_percorridos > 0 and obj.litros > 0:
                consumo = km_percorridos / obj.litros
                return {
                    'valor': round(consumo, 2),
                    'unidade': 'km/l',
                    'km_percorridos': km_percorridos,
                    'periodo_dias': (obj.data - abastecimento_anterior.data).days
                }
        
        return None
    
    def get_km_percorridos(self, obj: Abastecimento) -> Optional[int]:
        """Calcula quilômetros percorridos desde último abastecimento."""
        consumo_info = self.get_consumo_medio(obj)
        return consumo_info['km_percorridos'] if consumo_info else None
    
    def get_eficiencia(self, obj: Abastecimento) -> str:
        """Avalia eficiência do consumo."""
        consumo_info = self.get_consumo_medio(obj)
        if consumo_info:
            consumo = consumo_info['valor']
            if consumo >= 12:
                return _("Excelente")
            elif consumo >= 10:
                return _("Bom")
            elif consumo >= 8:
                return _("Regular")
            else:
                return _("Ruim")
        return _("Não disponível")
    
    def get_diferenca_km(self, obj: Abastecimento) -> Optional[int]:
        """Calcula diferença da quilometragem atual do veículo."""
        if obj.veiculo:
            return obj.km_atual - obj.veiculo.km_atual
        return None
    
    def get_alerta_consumo(self, obj: Abastecimento) -> Optional[str]:
        """Gera alertas sobre consumo anômalo."""
        consumo_info = self.get_consumo_medio(obj)
        if consumo_info:
            consumo = consumo_info['valor']
            if consumo < 5:
                return _("Consumo muito alto - verificar veículo")
            elif consumo > 20:
                return _("Consumo muito baixo - verificar dados")
        
        diferenca_km = self.get_diferenca_km(obj)
        if diferenca_km and diferenca_km < 0:
            return _("Quilometragem menor que a atual - verificar dados")
        
        return None

    
    # VALIDATION METHODS
    
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validações adicionais para abastecimentos."""
        self._validate_required_fields(data)
        self._validate_quilometragem(data)
        self._validate_valores_positivos(data)
        self._validate_data_abastecimento(data)
        self._validate_business_rules(data)
        
        return data
    
    def _validate_required_fields(self, data: Dict[str, Any]) -> None:
        """Valida campos obrigatórios."""
        required_fields = ['veiculo', 'data', 'km_atual', 'litros', 'valor_total']
        
        for field in required_fields:
            if field not in data or data[field] is None:
                raise serializers.ValidationError({
                    field: _("Este campo é obrigatório.")
                })
    
    def _validate_quilometragem(self, data: Dict[str, Any]) -> None:
        """Valida quilometragem informada."""
        veiculo = data.get('veiculo') or (self.instance.veiculo if self.instance else None)
        km_atual = data.get('km_atual')
        
        if veiculo and km_atual:
            # Verifica se a quilometragem não é menor que a atual do veículo
            if km_atual < veiculo.km_atual:
                raise serializers.ValidationError({
                    'km_atual': _(
                        "A quilometragem informada ({}) não pode ser menor "
                        "que a atual do veículo ({})."
                    ).format(km_atual, veiculo.km_atual)
                })
            
            # Verifica incremento razoável (máximo 2000km por abastecimento)
            diferenca = km_atual - veiculo.km_atual
            if diferenca > 2000:
                raise serializers.ValidationError({
                    'km_atual': _(
                        "Incremento muito alto de quilometragem ({}km). "
                        "Verifique o valor informado."
                    ).format(diferenca)
                })
    
    def _validate_valores_positivos(self, data: Dict[str, Any]) -> None:
        """Valida se valores são positivos."""
        positive_fields = ['km_atual', 'litros', 'valor_total']
        
        for field in positive_fields:
            value = data.get(field)
            if value is not None and value <= 0:
                raise serializers.ValidationError({
                    field: _("Este valor deve ser positivo.")
                })
    
    def _validate_data_abastecimento(self, data: Dict[str, Any]) -> None:
        """Valida data do abastecimento."""
        data_abastecimento = data.get('data')
        if data_abastecimento:
            hoje = date.today()
            
            # Não permite datas futuras
            if data_abastecimento > hoje:
                raise serializers.ValidationError({
                    'data': _("A data do abastecimento não pode ser futura.")
                })
            
            # Não permite datas muito antigas (mais de 1 ano)
            um_ano_atras = hoje - timedelta(days=365)
            if data_abastecimento < um_ano_atras:
                raise serializers.ValidationError({
                    'data': _("A data do abastecimento é muito antiga.")
                })
    
    def _validate_business_rules(self, data: Dict[str, Any]) -> None:
        """Aplica regras de negócio específicas."""
        veiculo = data.get('veiculo')
        data_abastecimento = data.get('data')
        
        if veiculo and data_abastecimento:
            # Verifica se já existe abastecimento na mesma data
            existing_abastecimento = veiculo.abastecimentos.filter(
                data=data_abastecimento
            )
            
            if self.instance:
                existing_abastecimento = existing_abastecimento.exclude(
                    id=self.instance.id
                )
            
            if existing_abastecimento.exists():
                raise serializers.ValidationError({
                    'data': _("Já existe um abastecimento registrado nesta data.")
                })
            
            # Valida consumo razoável
            litros = data.get('litros')
            if litros and litros > 100:  # Tanque muito grande
                raise serializers.ValidationError({
                    'litros': _("Quantidade muito alta de combustível.")
                })

    
    # CRUD METHODS
    
    
    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> Abastecimento:
        """
        Cria novo abastecimento e atualiza quilometragem do veículo.
        """
        instance = super().create(validated_data)
        self._update_veiculo_km(instance)
        return instance
    
    @transaction.atomic
    def update(self, instance: Abastecimento, validated_data: Dict[str, Any]) -> Abastecimento:
        """
        Atualiza abastecimento e quilometragem do veículo se necessário.
        """
        instance = super().update(instance, validated_data)
        
        if 'km_atual' in validated_data:
            self._update_veiculo_km(instance)
        
        return instance
    
    def _update_veiculo_km(self, abastecimento: Abastecimento) -> None:
        """Atualiza quilometragem do veículo se necessário."""
        veiculo = abastecimento.veiculo
        
        # Busca o maior km registrado para este veículo
        maior_km = veiculo.abastecimentos.aggregate(
            max_km=Max('km_atual')
        )['max_km']
        
        if maior_km and maior_km > veiculo.km_atual:
            veiculo.km_atual = maior_km
            veiculo.save(update_fields=['km_atual'])


class VeiculoSerializer(BaseModelSerializer):
    """
    Serializer completo para o modelo Veiculo.
    
    Usado para operações CRUD completas por administradores e membros
    de guarnição, incluindo relacionamentos e estatísticas.
    """
    
    
    # RELATIONSHIP FIELDS
    
    
    modelo_display = CharField(source='get_modelo_display', read_only=True)
    guarnicao_info = serializers.SerializerMethodField()
    
    
    # STATISTICAL FIELDS
    
    
    fotos_count = serializers.SerializerMethodField()
    abastecimentos_count = serializers.SerializerMethodField()
    ultimo_abastecimento = serializers.SerializerMethodField()
    consumo_medio_geral = serializers.SerializerMethodField()
    
    
    # STATUS FIELDS
    
    
    status_manutencao = serializers.SerializerMethodField()
    proximidade_manutencao = serializers.SerializerMethodField()
    disponibilidade = serializers.SerializerMethodField()
    
    class Meta:
        model = Veiculo
        fields = [
            'id', 'placa', 'modelo', 'modelo_display', 'em_condicao',
            'observacao', 'km_atual', 'guarnicao_info',
            'fotos_count', 'abastecimentos_count', 'ultimo_abastecimento',
            'consumo_medio_geral', 'status_manutencao', 'proximidade_manutencao',
            'disponibilidade', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'modelo_display', 'guarnicao_info',
            'fotos_count', 'abastecimentos_count', 'ultimo_abastecimento',
            'consumo_medio_geral', 'status_manutencao', 'proximidade_manutencao',
            'disponibilidade'
        ]

    
    # SERIALIZER METHOD FIELDS
    
    
    def get_guarnicao_info(self, obj: Veiculo) -> Optional[Dict[str, Any]]:
        """Retorna informações da guarnição associada."""
        if hasattr(obj, 'guarnicao_associada') and obj.guarnicao_associada:
            return {
                'id': obj.guarnicao_associada.id,
                'name': obj.guarnicao_associada.name,
                'operacao': obj.guarnicao_associada.operacao.name,
                'comandante': obj.guarnicao_associada.comandante.name if obj.guarnicao_associada.comandante else None
            }
        return None
    
    def get_fotos_count(self, obj: Veiculo) -> int:
        """Conta número de fotos associadas."""
        return obj.fotos.count()
    
    def get_abastecimentos_count(self, obj: Veiculo) -> int:
        """Conta número de abastecimentos registrados."""
        return obj.abastecimentos.count()
    
    def get_ultimo_abastecimento(self, obj: Veiculo) -> Optional[Dict[str, Any]]:
        """Retorna informações do último abastecimento."""
        ultimo = obj.abastecimentos.order_by('-data').first()
        if ultimo:
            return {
                'data': ultimo.data,
                'km': ultimo.km_atual,
                'litros': ultimo.litros,
                'valor': ultimo.valor_total,
                'dias_atras': (date.today() - ultimo.data).days
            }
        return None
    
    def get_consumo_medio_geral(self, obj: Veiculo) -> Optional[Dict[str, Any]]:
        """Calcula consumo médio geral do veículo."""
        abastecimentos = obj.abastecimentos.order_by('data')
        
        if abastecimentos.count() < 2:
            return None
        
        primeiro = abastecimentos.first()
        ultimo = abastecimentos.last()
        
        km_total = ultimo.km_atual - primeiro.km_atual
        litros_total = abastecimentos.aggregate(
            total=Sum('litros')
        )['total'] or 0
        
        if km_total > 0 and litros_total > 0:
            consumo = km_total / litros_total
            return {
                'valor': round(consumo, 2),
                'unidade': 'km/l',
                'km_analisados': km_total,
                'litros_totais': litros_total,
                'periodo_dias': (ultimo.data - primeiro.data).days
            }
        
        return None
    
    def get_status_manutencao(self, obj: Veiculo) -> Dict[str, Any]:
        """Avalia status de manutenção do veículo."""
        status = "operacional" if obj.em_condicao else "manutencao"
        
        # Análise baseada em quilometragem
        alertas = []
        if obj.km_atual > 100000:
            alertas.append("Alta quilometragem")
        
        # Análise baseada em último abastecimento
        ultimo_abastecimento = self.get_ultimo_abastecimento(obj)
        if ultimo_abastecimento and ultimo_abastecimento['dias_atras'] > 30:
            alertas.append("Sem abastecimento há mais de 30 dias")
        
        return {
            'status': status,
            'em_condicao': obj.em_condicao,
            'alertas': alertas,
            'requer_atencao': len(alertas) > 0 or not obj.em_condicao
        }
    
    def get_proximidade_manutencao(self, obj: Veiculo) -> Dict[str, Any]:
        """Calcula proximidade de manutenção preventiva."""
        # Estimativa simples: manutenção a cada 10.000km
        km_para_manutencao = 10000 - (obj.km_atual % 10000)
        percentual = ((obj.km_atual % 10000) / 10000) * 100
        
        if percentual >= 90:
            urgencia = "critica"
        elif percentual >= 75:
            urgencia = "alta"
        elif percentual >= 50:
            urgencia = "media"
        else:
            urgencia = "baixa"
        
        return {
            'km_para_manutencao': km_para_manutencao,
            'percentual_concluido': round(percentual, 1),
            'urgencia': urgencia,
            'necessita_agendamento': percentual >= 75
        }
    
    def get_disponibilidade(self, obj: Veiculo) -> str:
        """Determina disponibilidade do veículo."""
        if not obj.em_condicao:
            return "indisponivel"
        
        if hasattr(obj, 'guarnicao_associada') and obj.guarnicao_associada:
            return "em_uso"
        
        return "disponivel"

    
    # VALIDATION METHODS
    
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validações adicionais para veículos."""
        self._validate_placa(data)
        self._validate_km_atual(data)
        self._validate_business_rules(data)
        
        # Aplica validações do modelo
        instance = Veiculo(**data)
        if self.instance:
            for attr, value in data.items():
                setattr(self.instance, attr, value)
            instance = self.instance
        
        instance.clean()
        return data
    
    def _validate_placa(self, data: Dict[str, Any]) -> None:
        """Valida formato e unicidade da placa."""
        placa = data.get('placa')
        if placa:
            # Remove espaços e converte para maiúsculo
            placa = placa.strip().upper()
            data['placa'] = placa
            
            # Verifica duplicação
            existing = Veiculo.objects.filter(placa=placa)
            if self.instance:
                existing = existing.exclude(id=self.instance.id)
            
            if existing.exists():
                raise serializers.ValidationError({
                    'placa': _("Já existe um veículo com esta placa.")
                })
    
    def _validate_km_atual(self, data: Dict[str, Any]) -> None:
        """Valida quilometragem atual."""
        km_atual = data.get('km_atual')
        if km_atual is not None:
            if km_atual < 0:
                raise serializers.ValidationError({
                    'km_atual': _("A quilometragem não pode ser negativa.")
                })
            
            if km_atual > 999999:
                raise serializers.ValidationError({
                    'km_atual': _("Quilometragem muito alta.")
                })
    
    def _validate_business_rules(self, data: Dict[str, Any]) -> None:
        """Aplica regras de negócio específicas."""
        # Se estiver em manutenção, não pode estar associado a guarnição
        em_condicao = data.get('em_condicao')
        if em_condicao is False:
            if self.instance and hasattr(self.instance, 'guarnicao_associada'):
                if self.instance.guarnicao_associada:
                    raise serializers.ValidationError({
                        'em_condicao': _(
                            "Veículo em uso por guarnição não pode ser "
                            "marcado como em manutenção."
                        )
                    })



# RECURSIVE SERIALIZERS


class VeiculoRecursivoSerializer(BaseModelSerializer):
    """
    Serializer recursivo completo para veículos.
    
    Inclui informações detalhadas de fotos, abastecimentos e
    relacionamentos em uma estrutura hierárquica otimizada.
    """
    
    
    # RELATIONSHIP FIELDS
    
    
    fotos = FotoVeiculoBasicSerializer(many=True, read_only=True)
    abastecimentos = serializers.SerializerMethodField()
    guarnicao_completa = serializers.SerializerMethodField()
    
    
    # STATISTICAL FIELDS
    
    
    estatisticas = serializers.SerializerMethodField()
    historico_consumo = serializers.SerializerMethodField()
    analise_uso = serializers.SerializerMethodField()
    
    class Meta:
        model = Veiculo
        fields = [
            'id', 'placa', 'modelo', 'em_condicao', 'observacao', 'km_atual',
            'fotos', 'abastecimentos', 'guarnicao_completa',
            'estatisticas', 'historico_consumo', 'analise_uso'
        ]

    
    # SERIALIZER METHOD FIELDS
    
    
    def get_abastecimentos(self, obj: Veiculo) -> List[Dict[str, Any]]:
        """Obtém histórico de abastecimentos."""
        abastecimentos = obj.abastecimentos.order_by('-data')[:10]  # Últimos 10
        return AbastecimentoBasicSerializer(abastecimentos, many=True).data
    
    def get_guarnicao_completa(self, obj: Veiculo) -> Optional[Dict[str, Any]]:
        """Retorna informações completas da guarnição."""
        if hasattr(obj, 'guarnicao_associada') and obj.guarnicao_associada:
            guarnicao = obj.guarnicao_associada
            return {
                'id': guarnicao.id,
                'nome': guarnicao.name,
                'operacao': {
                    'id': guarnicao.operacao.id,
                    'nome': guarnicao.operacao.name,
                    'ativa': guarnicao.operacao.is_active
                },
                'comandante': {
                    'id': guarnicao.comandante.id,
                    'nome': guarnicao.comandante.name
                } if guarnicao.comandante else None,
                'total_membros': guarnicao.membros.count()
            }
        return None
    
    def get_estatisticas(self, obj: Veiculo) -> Dict[str, Any]:
        """Gera estatísticas completas do veículo."""
        abastecimentos = obj.abastecimentos.all()
        
        if not abastecimentos.exists():
            return {
                'total_abastecimentos': 0,
                'total_gastos': 0,
                'total_litros': 0,
                'consumo_medio': None
            }
        
        stats = abastecimentos.aggregate(
            total_gastos=Sum('valor_total'),
            total_litros=Sum('litros'),
            media_litros=Avg('litros'),
            media_valor=Avg('valor_total')
        )
        
        # Calcula consumo médio geral
        consumo_info = VeiculoSerializer().get_consumo_medio_geral(obj)
        
        return {
            'total_abastecimentos': abastecimentos.count(),
            'total_gastos': stats['total_gastos'] or 0,
            'total_litros': stats['total_litros'] or 0,
            'media_litros_por_abastecimento': round(stats['media_litros'] or 0, 2),
            'media_valor_por_abastecimento': round(stats['media_valor'] or 0, 2),
            'consumo_medio_geral': consumo_info,
            'total_fotos': obj.fotos.count()
        }
    
    def get_historico_consumo(self, obj: Veiculo) -> List[Dict[str, Any]]:
        """Gera histórico de consumo por mês."""
        from django.db.models import Extract
        
        # Agrupa abastecimentos por mês
        consumo_mensal = obj.abastecimentos.annotate(
            mes=Extract('data', 'month'),
            ano=Extract('data', 'year')
        ).values('ano', 'mes').annotate(
            total_litros=Sum('litros'),
            total_valor=Sum('valor_total'),
            total_abastecimentos=Count('id')
        ).order_by('-ano', '-mes')[:12]  # Últimos 12 meses
        
        return [
            {
                'periodo': f"{item['mes']:02d}/{item['ano']}",
                'total_litros': item['total_litros'],
                'total_valor': item['total_valor'],
                'total_abastecimentos': item['total_abastecimentos'],
                'valor_medio_litro': round(
                    item['total_valor'] / item['total_litros'], 2
                ) if item['total_litros'] > 0 else 0
            }
            for item in consumo_mensal
        ]
    
    def get_analise_uso(self, obj: Veiculo) -> Dict[str, Any]:
        """Gera análise de uso do veículo."""
        hoje = date.today()
        ultimo_abastecimento = obj.abastecimentos.order_by('-data').first()
        
        # Calcula período de inatividade
        dias_sem_uso = 0
        if ultimo_abastecimento:
            dias_sem_uso = (hoje - ultimo_abastecimento.data).days
        
        # Avalia padrão de uso
        if dias_sem_uso == 0:
            padrao_uso = "uso_intenso"
        elif dias_sem_uso <= 7:
            padrao_uso = "uso_regular"
        elif dias_sem_uso <= 30:
            padrao_uso = "uso_esporadico"
        else:
            padrao_uso = "inativo"
        
        return {
            'dias_sem_abastecimento': dias_sem_uso,
            'padrao_uso': padrao_uso,
            'disponibilidade': VeiculoSerializer().get_disponibilidade(obj),
            'status_manutencao': VeiculoSerializer().get_status_manutencao(obj),
            'recomendacoes': self._generate_recomendacoes(obj, dias_sem_uso)
        }
    
    def _generate_recomendacoes(self, obj: Veiculo, dias_sem_uso: int) -> List[str]:
        """Gera recomendações baseadas no uso do veículo."""
        recomendacoes = []
        
        if not obj.em_condicao:
            recomendacoes.append("Verificar status de manutenção")
        
        if dias_sem_uso > 30:
            recomendacoes.append("Veículo inativo há muito tempo - verificar necessidade")
        
        consumo_info = VeiculoSerializer().get_consumo_medio_geral(obj)
        if consumo_info and consumo_info['valor'] < 6:
            recomendacoes.append("Consumo alto - verificar manutenção")
        
        proximidade = VeiculoSerializer().get_proximidade_manutencao(obj)
        if proximidade['necessita_agendamento']:
            recomendacoes.append("Agendar manutenção preventiva")
        
        return recomendacoes
