from typing import Dict, Any, List, Optional
from uuid import UUID

# Django Core
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Django REST Framework
from rest_framework import serializers
from rest_framework.fields import CharField, UUIDField, BooleanField

# Local Apps
from arcanosig.oper.models.operacao import (
    Operacao,
    Guarnicao,
    GuarnicaoMembro,
)
from arcanosig.oper.models.cautela import (
    CautelaIndividual,
)
from arcanosig.oper.serializers.base_serializers import (
    BaseModelSerializer, 
    UserSerializer,
)

from arcanosig.oper.models.veiculo import Veiculo
from arcanosig.users.models import User



# BASIC SERIALIZERS

class VeiculoBasicSerializer(BaseModelSerializer):
    """
    Serializer básico para informações essenciais de veículos.
    Usado em contextos onde apenas informações básicas são necessárias,
    como em listagens de guarnições e operações.
    """
    modelo_display = CharField(source='get_modelo_display', read_only=True)
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = Veiculo
        fields = [
            'id', 'placa', 'modelo', 'modelo_display',
            'em_condicao', 'status_display', 'km_atual'
        ]
        read_only_fields = fields

    def get_status_display(self, obj: Veiculo) -> str:
        """Retorna status legível do veículo."""
        if obj.em_condicao:
            return _("Operacional")
        return _("Manutenção")

class CautelaBasicSerializer(BaseModelSerializer):
    """
    Serializer básico para cautelas individuais.
    Fornece informações essenciais sobre cautelas sem carregar
    dados desnecessários para listagens simples.
    """
    item_nome = CharField(source='item.nome', read_only=True)
    item_codigo = CharField(source='item.codigo', read_only=True)
    policial_nome = CharField(source='policial.name', read_only=True)
    status_display = serializers.SerializerMethodField()
    tempo_cautela = serializers.SerializerMethodField()

    class Meta:
        model = CautelaIndividual
        fields = [
            'id', 'item', 'item_nome', 'item_codigo',
            'policial', 'policial_nome', 'guarnicao',
            'data_cautela', 'devolvido', 'status_display',
            'tempo_cautela'
        ]
        read_only_fields = [
            'item_nome', 'item_codigo', 'policial_nome',
            'status_display', 'tempo_cautela'
        ]

    def get_status_display(self, obj: CautelaIndividual) -> str:
        """Retorna status legível da cautela."""
        if obj.devolvido:
            return _("Devolvido")
        return _("Em uso")

    def get_tempo_cautela(self, obj: CautelaIndividual) -> str:
        """Calcula tempo desde a cautela."""
        if not obj.data_cautela:
            return ""
        agora = timezone.now()
        delta = agora - obj.data_cautela
        if delta.days > 0:
            return _("%(days)d dias") % {'days': delta.days}
        elif delta.seconds >= 3600:
            horas = delta.seconds // 3600
            return _("%(hours)d horas") % {'hours': horas}
        else:
            return _("Hoje")


# USER CONTEXT SERIALIZERS

class PoliciaisCautelasSerializer(BaseModelSerializer):
    """
    Serializer para policiais com suas cautelas associadas.
    Contexto específico para visualização de policiais dentro de guarnições,
    incluindo suas cautelas ativas e estatísticas relevantes.
    """
    
    # BASIC FIELDS
    
    cautelas = serializers.SerializerMethodField()
    total_cautelas = serializers.SerializerMethodField()
    cautelas_ativas = serializers.SerializerMethodField()
    
    # COMPUTED FIELDS
    
    status_cautelas = serializers.SerializerMethodField()
    ultima_cautela = serializers.SerializerMethodField()
    pode_receber_cautela = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'name', 'email', 'patente',
            'cautelas', 'total_cautelas', 'cautelas_ativas',
            'status_cautelas', 'ultima_cautela', 'pode_receber_cautela'
        ]
        read_only_fields = fields

    
    # SERIALIZER METHOD FIELDS
    
    def get_cautelas(self, obj: User) -> List[Dict[str, Any]]:
        """Obtém cautelas associadas ao policial na guarnição atual."""
        guarnicao_id = self.context.get('guarnicao_id')
        if not guarnicao_id:
            return []
        # Assuming cautelaindividual_set is prefetched
        cautelas = getattr(obj, 'cautelaindividual_set', []).filter(guarnicao_id=guarnicao_id)
        return CautelaBasicSerializer(cautelas, many=True).data

    def get_total_cautelas(self, obj: User) -> int:
        """Conta total de cautelas do policial na guarnição."""
        guarnicao_id = self.context.get('guarnicao_id')
        if not guarnicao_id:
            return 0
        # Assuming cautelaindividual_set is prefetched
        return getattr(obj, 'cautelaindividual_set', []).filter(guarnicao_id=guarnicao_id).count()

    def get_cautelas_ativas(self, obj: User) -> int:
        """Conta cautelas não devolvidas."""
        guarnicao_id = self.context.get('guarnicao_id')
        if not guarnicao_id:
            return 0
        # Assuming cautelaindividual_set is prefetched
        return getattr(obj, 'cautelaindividual_set', []).filter(
            guarnicao_id=guarnicao_id,
            devolvido=False
        ).count()

    def get_status_cautelas(self, obj: User) -> str:
        """Retorna status geral das cautelas do policial."""
        cautelas_ativas = self.get_cautelas_ativas(obj)
        if cautelas_ativas == 0:
            return _("Sem cautelas")
        elif cautelas_ativas <= 3:
            return _("Normal")
        elif cautelas_ativas <= 5:
            return _("Atenção")
        else:
            return _("Crítico")

    def get_ultima_cautela(self, obj: User) -> Optional[Dict[str, Any]]:
        """Retorna informações da última cautela."""
        guarnicao_id = self.context.get('guarnicao_id')
        if not guarnicao_id:
            return None
        # Assuming cautelaindividual_set is prefetched
        ultima = sorted(
            getattr(obj, 'cautelaindividual_set', []).filter(guarnicao_id=guarnicao_id),
            key=lambda x: x.data_cautela,
            reverse=True
        )
        if ultima:
            ultima = ultima[0]
            return {
                'item': ultima.item.nome,
                'data': ultima.data_cautela,
                'devolvido': ultima.devolvido
            }
        return None

    def get_pode_receber_cautela(self, obj: User) -> bool:
        """Verifica se o policial pode receber nova cautela."""
        # Regra de negócio: máximo 10 cautelas ativas
        cautelas_ativas = self.get_cautelas_ativas(obj)
        return cautelas_ativas < 10


class GuarnicaoSerializer(serializers.ModelSerializer):
    """
    Serializer para o modelo Guarnicao.
    Usado para criar, atualizar e visualizar detalhes de uma guarnição.
    """
    # Campos que representam IDs de relacionamentos
    # O ModelSerializer lida com a validação e atribuição automática
    # se os nomes dos campos corresponderem aos nomes dos campos do modelo.
    comandante_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), # Valida se o ID existe no modelo User
        source='comandante',        # Mapeia para o campo 'comandante' do modelo
        write_only=True,            # Torna este campo apenas para escrita (não aparece na saída)
        help_text="ID do usuário que é o comandante desta guarnição."
    )
    
    operacao = serializers.PrimaryKeyRelatedField(
        queryset=Operacao.objects.all(),
        help_text="ID da operação à qual esta guarnição pertence."
    )
    veiculo = serializers.PrimaryKeyRelatedField(
        queryset=Veiculo.objects.all(),
        allow_null=True,
        required=False, # Marcar como não obrigatório na entrada
        help_text="ID do veículo associado a esta guarnição (opcional)."
    )

    class Meta:
        model = Guarnicao
        # Incluímos o 'id' para que ele seja retornado após a criação
        fields = ['id', 'name', 'operacao', 'comandante_id', 'veiculo', 'created_at']
        # Campos apenas para leitura (retornados na resposta, mas não necessários na entrada)
        read_only_fields = ['created_at']


class GuarnicaoMembroSerializer(BaseModelSerializer):
    """
    Serializer para o modelo GuarnicaoMembro com informações detalhadas.
    Gerencia a associação entre usuários e guarnições, incluindo
    validações de negócio e informações contextuais da operação.
    """
    
    # RELATIONSHIP FIELDS
    
    # ID do registro GuarnicaoMembro para operações de remoção
    id_membro = UUIDField(source='id', read_only=True)
    # Informações do usuário
    user = UserSerializer(read_only=True)
    user_id = UUIDField(write_only=True)
    # Informações da guarnição
    guarnicao_id = UUIDField(write_only=True)
    id_guarnicao = UUIDField(source='guarnicao.id', read_only=True)
    nome_guarnicao = CharField(source='guarnicao.name', read_only=True)
    # Informações da operação
    id_operacao = UUIDField(source='guarnicao.operacao.id', read_only=True)
    nome_operacao = CharField(source='guarnicao.operacao.name', read_only=True)
    
    # COMPUTED FIELDS
    
    is_comandante = serializers.SerializerMethodField()
    tempo_na_guarnicao = serializers.SerializerMethodField()
    status_membro = serializers.SerializerMethodField()

    class Meta:
        model = GuarnicaoMembro
        fields = [
            'id_membro', 'user', 'user_id', 'guarnicao_id',
            'id_guarnicao', 'nome_guarnicao',
            'id_operacao', 'nome_operacao',
            'is_comandante', 'tempo_na_guarnicao', 'status_membro',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id_membro', 'user', 'id_guarnicao', 'nome_guarnicao',
            'id_operacao', 'nome_operacao', 'is_comandante',
            'tempo_na_guarnicao', 'status_membro', 'created_at', 'updated_at'
        ]

    
    # SERIALIZER METHOD FIELDS
    
    def get_is_comandante(self, obj: GuarnicaoMembro) -> bool:
        """Verifica se o membro é comandante da guarnição."""
        return obj.guarnicao.comandante == obj.user

    def get_tempo_na_guarnicao(self, obj: GuarnicaoMembro) -> str:
        """Calcula tempo como membro da guarnição."""
        if not obj.created_at:
            return ""
        agora = timezone.now()
        delta = agora - obj.created_at
        if delta.days > 0:
            return _("%(days)d dias") % {'days': delta.days}
        elif delta.seconds >= 3600:
            horas = delta.seconds // 3600
            return _("%(hours)d horas") % {'hours': horas}
        else:
            return _("Recém adicionado")

    def get_status_membro(self, obj: GuarnicaoMembro) -> str:
        """Retorna status do membro na guarnição."""
        if obj.guarnicao.comandante == obj.user:
            return _("Comandante")
        return _("Membro")

    
    # VALIDATION METHODS
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validações adicionais para membros de guarnição."""
        self._validate_required_fields(data)
        self._validate_guarnicao(data)
        self._validate_user(data)
        self._validate_business_rules(data)
        return data

    def _validate_required_fields(self, data: Dict[str, Any]) -> None:
        """Valida campos obrigatórios."""
        if 'guarnicao_id' not in data:
            raise serializers.ValidationError({
                'guarnicao_id': _("A guarnição é obrigatória.")
            })
        if 'user_id' not in data:
            raise serializers.ValidationError({
                'user_id': _("O ID do usuário é obrigatório.")
            })

    def _validate_guarnicao(self, data: Dict[str, Any]) -> None:
        """Valida e obtém a guarnição."""
        try:
            guarnicao_id = data['guarnicao_id']
            guarnicao = Guarnicao.objects.select_related('operacao').get(id=guarnicao_id)
            data['guarnicao_obj'] = guarnicao
        except Guarnicao.DoesNotExist:
            raise serializers.ValidationError({
                'guarnicao_id': _("Guarnição não encontrada.")
            })
        except (ValueError, TypeError):
            raise serializers.ValidationError({
                'guarnicao_id': _("ID de guarnição inválido.")
            })

    def _validate_user(self, data: Dict[str, Any]) -> None:
        """Valida e obtém o usuário."""
        try:
            user_id = data['user_id']
            user = User.objects.get(id=user_id)
            data['user_obj'] = user
        except User.DoesNotExist:
            raise serializers.ValidationError({
                'user_id': _("Usuário não encontrado.")
            })
        except (ValueError, TypeError):
            raise serializers.ValidationError({
                'user_id': _("ID de usuário inválido.")
            })

    def _validate_business_rules(self, data: Dict[str, Any]) -> None:
        """Aplica regras de negócio."""
        guarnicao = data['guarnicao_obj']
        user = data['user_obj']

        # Verifica se a operação está ativa
        if not guarnicao.operacao.is_active:
            raise serializers.ValidationError({
                'non_field_errors': [
                    _("Não é possível adicionar membros em operações inativas.")
                ]
            })

        # Verifica duplicação na mesma guarnição
        if GuarnicaoMembro.objects.filter(guarnicao=guarnicao, user=user).exists():
            raise serializers.ValidationError({
                'non_field_errors': [
                    _("Este usuário já é membro desta guarnição.")
                ]
            })

        # Verifica se já é membro de outra guarnição na mesma operação
        if GuarnicaoMembro.objects.filter(
            guarnicao__operacao=guarnicao.operacao,
            user=user
        ).exists():
             raise serializers.ValidationError({
                 'non_field_errors': [
                     _("Este usuário já está alocado em outra guarnição nesta operação.")
                 ]
             })

    
    # CREATE/UPDATE METHODS
    
    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> GuarnicaoMembro:
        """Cria um novo membro de guarnição."""
        guarnicao = validated_data['guarnicao_obj']
        user = validated_data['user_obj']

        # Remove temporary objects from validated_data before calling super()
        validated_data.pop('guarnicao_obj')
        validated_data.pop('user_obj')

        # Create the GuarnicaoMembro instance
        guarnicao_membro = GuarnicaoMembro.objects.create(
            guarnicao=guarnicao,
            user=user
        )
        return guarnicao_membro

    @transaction.atomic
    def update(self, instance: GuarnicaoMembro, validated_data: Dict[str, Any]) -> GuarnicaoMembro:
        """Atualiza um membro de guarnição (geralmente não usado para este modelo)."""
        # For GuarnicaoMembro, updates are typically not allowed via this serializer
        # as the association is fixed. If updates were needed (e.g., changing role),
        # custom logic would be added here.
        # As per the model's nature, we'll prevent updates or handle specific fields.
        # For now, we'll just return the instance as no updates are expected.
        # If user_id or guarnicao_id were passed in update, they would be validated
        # but not used to change the instance's FKs directly by default `update`.
        # To allow changing user/guarnicao, custom logic is needed.
        # Assuming updates are not intended for user/guarnicao FKs:
        return instance


# RECURSIVE/DETAIL SERIALIZERS


class GuarnicaoRecursivaSerializer(BaseModelSerializer):
    """
    Serializer detalhado para Guarnicao, usado em contextos recursivos.
    Inclui membros com suas cautelas e informações do veículo.
    Otimizado para uso dentro do OperacaoRecursivaSerializer.
    """
    comandante = UserSerializer(read_only=True)
    veiculo = serializers.SerializerMethodField() # Use method field for vehicle
    membros = serializers.SerializerMethodField()
    cautelas = serializers.SerializerMethodField() # Cautelas directly on guarnicao
    status_completo = serializers.SerializerMethodField()
    efetivo_atual = serializers.SerializerMethodField()

    class Meta:
        model = Guarnicao
        fields = [
            'id', 'name', 'operacao', 'comandante', 'veiculo',
            'membros', 'cautelas', 'status_completo', 'efetivo_atual',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_veiculo(self, obj: Guarnicao) -> Optional[Dict[str, Any]]:
        """Retorna dados do veículo se existir."""
        if obj.veiculo:
            return VeiculoBasicSerializer(obj.veiculo).data
        return None

    def get_total_veiculos(self, obj: Guarnicao) -> int:
        """Conta total de veículos (apenas o veículo principal)."""
        # Assuming 'veiculo' is a ForeignKey/OneToOneField
        return 1 if obj.veiculo else 0

    def get_cautelas(self, obj: Guarnicao) -> List[Dict[str, Any]]:
        """Obtém cautelas da guarnição (diretamente associadas)."""
        # Assuming 'cautelas_guarnicao' is a reverse relation from CautelaIndividual
        # Use prefetched data if available
        cautelas = getattr(obj, 'cautelas_guarnicao', [])
        return CautelaBasicSerializer(cautelas, many=True).data

    def get_total_cautelas(self, obj: Guarnicao) -> int:
        """Conta total de cautelas associadas à guarnição."""
        # Use prefetched data count if available
        return len(getattr(obj, 'cautelas_guarnicao', []))


    def get_status_completo(self, obj: Guarnicao) -> Dict[str, Any]:
        """Status detalhado da guarnição."""
        # Reuse logic from GuarnicaoSerializer
        return GuarnicaoSerializer().get_status_operacional(obj)

    def get_efetivo_atual(self, obj: Guarnicao) -> Dict[str, Any]:
        """Informações do efetivo atual."""
        tem_comandante = bool(obj.comandante)
        # Access prefetched members
        members_list = list(getattr(obj, 'membros', []))
        membros_count = len(members_list)
        total = membros_count + (1 if tem_comandante and obj.comandante not in members_list else 0)

        status = _("Incompleto")
        if tem_comandante and membros_count >= 1:
             status = _("Completo")
        elif tem_comandante:
             status = _("Sem membros")
        elif membros_count >= 1:
             status = _("Sem comandante")
        else:
             status = _("Vazio")


        return {
            'comandante': tem_comandante,
            'membros': membros_count,
            'total': total,
            'status': status
        }

    def get_membros(self, obj) -> List[Dict[str, Any]]: # Removido a type hint Guarnicao aqui
        """Retorna resumo dos membros."""
        membros_list = []

        if isinstance(obj, dict):
            # Se obj for um dicionário, 'membros' deve ser uma lista de IDs
            membros_ids = obj.get('membros', [])
            limited_ids = membros_ids[:5]
            if limited_ids:
                users = User.objects.filter(id__in=limited_ids)
                for user in users:
                     membros_list.append({
                        'id': str(user.id), # Assumindo que User ID é UUID
                        'nome': user.name, # Use um campo de nome apropriado
                        'patente': getattr(user, 'patent', 'N/A'), 
                    })
        else:
            for membro in obj.membros.all()[:5]:
                 membros_list.append({
                    'id': str(membro.id), # Assumindo que Membro/User ID é UUID
                    'nome': user.name, # Use um campo de nome apropriado
                    'patente': getattr(membro, 'patent', 'N/A'),
                })
                
        return membros_list
    
class OperacaoSerializer(BaseModelSerializer):
    """
    Serializer completo para o modelo Operacao.
    Usado para operações CRUD por administradores, incluindo
    validações de negócio e campos computados relevantes.
    """
    total_guarnicoes = serializers.SerializerMethodField()
    total_membros = serializers.SerializerMethodField()
    total_veiculos = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    duracao_prevista = serializers.SerializerMethodField()
    progresso = serializers.SerializerMethodField()

    class Meta:
        model = Operacao
        fields = [
            'id', 'name', 'description', 'start_date', 'end_date',
            'is_active', 'total_guarnicoes', 'total_membros',
            'total_veiculos', 'status_display', 'duracao_prevista',
            'progresso', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'total_guarnicoes',
            'total_membros', 'total_veiculos', 'status_display',
            'duracao_prevista', 'progresso'
        ]

    def get_total_guarnicoes(self, obj: Operacao) -> int:
        """Conta total de guarnições."""
        return obj.guarnicoes.count()

    def get_total_membros(self, obj: Operacao) -> int:
        """Conta total de membros em todas as guarnições."""
        # Efficiently count members via aggregation
        return GuarnicaoMembro.objects.filter(
            guarnicao__operacao=obj
        ).count()

    def get_total_veiculos(self, obj: Operacao) -> int:
        """Conta total de veículos em uso (associados a guarnições)."""
        # Efficiently count guarnicoes with vehicles
        return obj.guarnicoes.filter(
            veiculo__isnull=False
        ).count()

    def get_status_display(self, obj: Operacao) -> str:
        """Retorna status legível da operação."""
        if not obj.is_active:
            return _("Inativa")
        agora = timezone.now().date()
        if obj.start_date and agora < obj.start_date:
            return _("Programada")
        elif obj.end_date and agora > obj.end_date:
            return _("Encerrada")
        else:
            return _("Em andamento")

    def get_duracao_prevista(self, obj: Operacao) -> Optional[str]:
        """Calcula duração prevista da operação."""
        if obj.start_date and obj.end_date:
            delta = obj.end_date - obj.start_date
            return _("%(days)d dias") % {'days': delta.days + 1}
        return None

    def get_progresso(self, obj: Operacao) -> Optional[Dict[str, Any]]:
        """Calcula progresso da operação."""
        if not (obj.start_date and obj.end_date and obj.is_active):
            return None
        agora = timezone.now().date()
        total_dias = (obj.end_date - obj.start_date).days + 1
        if total_dias <= 0: # Avoid division by zero or negative duration
             return None

        if agora < obj.start_date:
            dias_decorridos = 0
        elif agora > obj.end_date:
            dias_decorridos = total_dias
        else:
            dias_decorridos = (agora - obj.start_date).days + 1

        percentual = (dias_decorridos / total_dias) * 100
        return {
            'dias_decorridos': dias_decorridos,
            'total_dias': total_dias,
            'percentual': round(percentual, 2),
            'dias_restantes': max(0, total_dias - dias_decorridos)
        }

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validações adicionais da operação."""
        # Create a temporary instance or update the existing one for model validation
        instance = self.instance or Operacao()
        # Update instance attributes with validated data
        for attr, value in data.items():
             setattr(instance, attr, value)

        # Apply model's clean method for field-level and cross-field validation
        try:
            instance.clean()
        except serializers.ValidationError as e:
            # Re-raise Django's ValidationError as DRF's ValidationError
            raise serializers.ValidationError(e.message_dict)
        except Exception as e:
            # Catch other potential errors from clean() if necessary
            raise serializers.ValidationError({'non_field_errors': [str(e)]})

        return data

class OperacaoListSerializer(BaseModelSerializer):
    """
    Serializer otimizado para listagem de operações.
    Versão simplificada focada em performance para listagens
    e dashboards, incluindo apenas informações essenciais.
    """
    status_display = serializers.SerializerMethodField()
    total_guarnicoes = serializers.SerializerMethodField()

    class Meta:
        model = Operacao
        fields = [
            'id', 'name', 'start_date', 'end_date',
            'is_active', 'status_display', 'total_guarnicoes'
        ]
        read_only_fields = fields

    def get_status_display(self, obj: Operacao) -> str:
        """Status simplificado da operação."""
        # Reuse logic from OperacaoSerializer for consistency
        return OperacaoSerializer().get_status_display(obj)

    def get_total_guarnicoes(self, obj: Operacao) -> int:
        """Conta guarnições da operação."""
        return obj.guarnicoes.count()

class OperacaoRecursivaSerializer(BaseModelSerializer):
    """
    Serializer recursivo completo para operações.
    Inclui toda a hierarquia: operação -> guarnições -> membros -> cautelas
    Otimizado com prefetch_related para evitar N+1 queries.
    """
    guarnicoes = serializers.SerializerMethodField()
    total_guarnicoes = serializers.SerializerMethodField()
    estatisticas = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField() # Add status display

    class Meta:
        model = Operacao
        fields = [
            'id', 'name', 'description', 'start_date', 'end_date',
            'is_active', 'status_display', 'guarnicoes', 'total_guarnicoes', 'estatisticas'
        ]
        read_only_fields = fields # All fields are read-only for this recursive view

    def get_status_display(self, obj: Operacao) -> str:
         """Retorna status legível da operação."""
         return OperacaoSerializer().get_status_display(obj)

    def get_guarnicoes(self, obj: Operacao) -> List[Dict[str, Any]]:
        """Obtém guarnições com dados completos."""
        # Otimização com prefetch_related
        # Note: Prefetching members and their cautelas requires nested Prefetch
        guarnicoes = obj.guarnicoes.prefetch_related(
            'comandante', # Prefetch commander
            'veiculo',    # Prefetch vehicle
            Prefetch(
                'membros', # Prefetch members (Users)
                queryset=User.objects.prefetch_related(
                     Prefetch(
                         'cautelaindividual_set', # Prefetch cautelas for each member
                         queryset=CautelaIndividual.objects.select_related('item')
                     )
                )
            ),
            Prefetch(
                'cautelas_guarnicao', # Prefetch cautelas directly linked to guarnicao
                queryset=CautelaIndividual.objects.select_related('item', 'policial')
            )
        )
        # Use GuarnicaoRecursivaSerializer for nested representation
        return GuarnicaoRecursivaSerializer(guarnicoes, many=True).data


    def get_total_guarnicoes(self, obj: Operacao) -> int:
        """Conta total de guarnições."""
        # Can use prefetched data count if available, or query
        # return len(getattr(obj, '_prefetched_objects_cache', {}).get('guarnicoes', [])) # If prefetched
        return obj.guarnicoes.count() # Or query if not always prefetched

    def get_estatisticas(self, obj: Operacao) -> Dict[str, Any]:
        """Gera estatísticas completas da operação."""
        # Use aggregation for performance
        stats = obj.guarnicoes.aggregate(
            total_guarnicoes=Count('id'),
            guarnicoes_com_comandante=Count('id', filter=Q(comandante__isnull=False)),
            guarnicoes_com_veiculo=Count('id', filter=Q(veiculo__isnull=False)),
            # To count guarnicoes with at least one member, aggregate members per guarnicao
            # This requires a slightly more complex aggregation or iterating through prefetched data
        )

        # Count members and cautelas across all guarnicoes efficiently
        total_membros = GuarnicaoMembro.objects.filter(
            guarnicao__operacao=obj
        ).count()
        total_cautelas = CautelaIndividual.objects.filter(
            guarnicao__operacao=obj
        ).count()
        total_cautelas_ativas = CautelaIndividual.objects.filter(
            guarnicao__operacao=obj,
            devolvido=False
        ).count()

        # Calculate guarnicoes_com_membros and completas (comandante + >=1 membro + veiculo)
        # This is hard to do purely with a single aggregate on the Operacao model.
        # If guarnicoes are prefetched, we can iterate. If not, we might need a separate query or aggregation.
        # Let's assume guarnicoes are prefetched in get_guarnicoes and reuse that data if possible,
        # or perform a separate efficient count if not.
        # For simplicity and efficiency, let's use aggregation for counts where possible.
        # Counting guarnicoes with members requires joining GuarnicaoMembro.
        guarnicoes_com_membros = obj.guarnicoes.annotate(
             member_count=Count('membros')
        ).filter(member_count__gt=0).count()

        # A guarnicao is "completa" if it has a commander, a vehicle, and at least one member.
        guarnicoes_completas = obj.guarnicoes.annotate(
             member_count=Count('membros')
        ).filter(
             comandante__isnull=False,
             veiculo__isnull=False,
             member_count__gt=0
        ).count()


        return {
            'guarnicoes': {
                'total': stats['total_guarnicoes'],
                'com_comandante': stats['guarnicoes_com_comandante'],
                'com_veiculo': stats['guarnicoes_com_veiculo'],
                'com_membros': guarnicoes_com_membros,
                'completas': guarnicoes_completas,
            },
            'recursos_humanos': {
                'total_membros': total_membros,
                'media_por_guarnicao': round(total_membros / max(stats['total_guarnicoes'], 1), 2) if stats['total_guarnicoes'] > 0 else 0
            },
            'cautelas': {
                'total': total_cautelas,
                'ativas': total_cautelas_ativas
            }
        }

    def to_representation(self, instance: Operacao) -> Dict[str, Any]:
        """Customiza a representação final dos dados."""
        # Call the parent's to_representation to get the default data structure
        data = super().to_representation(instance)

        # Reorganize the data structure as requested
        return {
            "operacao": {
                "id": data['id'],
                "nome": data['name'],
                "descricao": data['description'],
                "data_inicio": data['start_date'],
                "data_fim": data['end_date'],
                "ativa": data['is_active'],
                "status_display": data['status_display'], # Include status display
            },
            "guarnicoes": data['guarnicoes'],
            "total_guarnicoes": data['total_guarnicoes'],
            "estatisticas": data['estatisticas']
        }

class GuarnicaoListSerializer(BaseModelSerializer):
    """
    Serializer otimizado para listagem de guarnições.
    Versão simplificada focada em performance para operações de listagem,
    incluindo apenas informações essenciais e campos computados leves.
    """
    comandante_info = serializers.SerializerMethodField()
    operacao_nome = CharField(source='operacao.name', read_only=True)
    veiculo_info = serializers.SerializerMethodField()
    total_membros = serializers.SerializerMethodField()
    membros = serializers.SerializerMethodField()
    status_resumo = serializers.SerializerMethodField()
    class Meta:
        model = Guarnicao
        fields = [
            'id', 'name', 'operacao', 'operacao_nome',
            'comandante_info', 'veiculo_info',
            'total_membros', 'membros', 'status_resumo'
        ]
        read_only_fields = fields
    def get_comandante_info(self, obj):
        # Verifica se obj é uma instância do modelo ou um dicionário
        if isinstance(obj, dict):
            comandante_id = obj.get('comandante')
            if comandante_id:
                # Tente buscar o usuário, se necessário, ou retorne apenas o ID
                # Dependendo da lógica que você quer aqui
                try:
                    from arcanosig.users.models import User # Importe seu modelo de usuário
                    user = User.objects.get(id=comandante_id)
                    return str(comandante_id) # Retorna o ID como string
                except User.DoesNotExist:
                    return None
            return None # Retorna None se 'comandante' não estiver no dict ou for None
        else:
            # Se for uma instância do modelo (o caso esperado para representação final)
            # Acessa o objeto relacionado normalmente
            if obj.comandante:
                return {
                    'id': str(obj.comandante.id), # Converte o ID para string
                    'nome': obj.comandante.name,
                    'patente': obj.comandante.patent,
                }
            return None # Retorna None se o comandante não estiver definido ou não for encontrado
    def get_veiculo_info(self, obj: Guarnicao) -> Optional[Dict[str, Any]]:
        """Retorna informações básicas do veículo."""
        veiculo_instance = None
        if isinstance(obj, dict):
            # Se obj for um dicionário (vindo de validated_data)
            # A chave 'veiculo' no dicionário provavelmente contém o ID do veículo
            veiculo_id = obj.get('veiculo')
            if veiculo_id:
                try:
                    # Tenta buscar a instância do Veiculo pelo ID
                    veiculo_instance = Veiculo.objects.get(id=veiculo_id)
                except Veiculo.DoesNotExist:
                    veiculo_instance = None # Veiculo não encontrado
        else:
            # Se obj for uma instância do modelo Guarnicao
            veiculo_instance = obj.veiculo
        # Agora, use a instância do veículo (se encontrada) para construir o dicionário
        if veiculo_instance:
            return {
                'placa': veiculo_instance.placa,
                'modelo': veiculo_instance.modelo,
                'em_condicao': veiculo_instance.em_condicao,
            }
        return None
    def get_total_membros(self, obj) -> int:
        """Retorna o total de membros na guarnição."""
        # Verifica se obj é um dicionário (ocorre durante create/update antes de salvar)
        if isinstance(obj, dict):
            # Acessa a lista de membros diretamente do dicionário validated_data
            # Assume que 'membros' é a chave que contém a lista de membros (IDs ou dados)
            membros_data = obj.get('membros', [])
            return len(membros_data)
        # Verifica se obj é uma instância do modelo Guarnicao (ocorre após salvar ou em list/retrieve)
        elif isinstance(obj, Guarnicao):
            # Acessa o relacionamento ManyToManyField 'membros' na instância do modelo
            return obj.membros.count()
        else:
            # Caso inesperado
            return 0
    def get_membros(self, obj) -> List[Dict[str, Any]]:
        """Retorna resumo dos membros."""
        membros_list = []
        if isinstance(obj, dict):
            # Se obj for um dicionário, 'membros' deve ser uma lista de IDs
            membros_ids = obj.get('membros', [])
            # Removido o limite de 5 IDs para buscar
            limited_ids = membros_ids
            if limited_ids:
                # Busca os objetos User correspondentes aos IDs
                users = User.objects.filter(id__in=limited_ids)
                # Cria a lista de dicionários com as informações dos usuários encontrados
                for user in users:
                     membros_list.append({
                         'id': str(user.id), # Assumindo que User ID é UUID
                         'nome': user.name, # Use um campo de nome apropriado
                         'patente': getattr(user, 'patent', 'N/A'),
                     })
        else:
            # Se obj for uma instância do modelo
            # Itera sobre todos os objetos membros relacionados (sem limite)
            for membro in obj.membros.all():
                 membros_list.append({
                     'id': str(membro.id), # Assumindo que Membro/User ID é UUID
                     'nome': membro.name, # Use um campo de nome apropriado
                     # Assumindo que 'patent' é um campo ou propriedade no seu modelo Membro/User
                     'patente': getattr(membro, 'patent', 'N/A'),
                 })
        return membros_list
    def get_status_resumo(self, obj) -> str:
        """Status resumido da guarnição."""
        comandante_presente = False
        membros_presentes = False
        veiculo_presente = False
        if isinstance(obj, dict):
            # Se obj for um dicionário, verifica a presença das chaves e seus valores
            comandante_presente = bool(obj.get('comandante')) # Verifica se a chave existe e o valor não é Falsy (None, vazio, etc.)
            membros_data = obj.get('membros')
            membros_presentes = bool(membros_data and len(membros_data) > 0) # Verifica se a chave existe, é uma lista e não está vazia
            veiculo_presente = bool(obj.get('veiculo')) # Verifica se a chave existe e o valor não é Falsy
        else:
            # Se obj for uma instância do modelo
            comandante_presente = bool(obj.comandante)
            membros_presentes = obj.membros.exists()
            veiculo_presente = bool(obj.veiculo)
        # Lógica para determinar o status com base nas verificações
        if comandante_presente and membros_presentes and veiculo_presente:
            return _("Completa")
        elif comandante_presente and membros_presentes:
            return _("Sem veículo")
        elif comandante_presente:
            return _("Sem membros")
        else:
            return _("Incompleta")