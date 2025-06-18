from typing import Dict, Any, Optional
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Django REST Framework
from rest_framework import serializers
from rest_framework.fields import (
    CharField, 
    BooleanField, 
    DateTimeField,
)

# Local Apps
from arcanosig.oper.models.notificacao import (
    Notificacao,
    TipoNotificacao,
)

from arcanosig.oper.serializers.base_serializers import BaseModelSerializer


class NotificacaoSerializer(BaseModelSerializer):
    """
    Serializer completo para o modelo Notificacao.
    
    Fornece funcionalidade completa para operações CRUD de notificações,
    com controle específico para marcar como lida/não lida e validações
    de negócio apropriadas.
    
    Campos principais:
    - Dados básicos: titulo, mensagem, tipo, link
    - Estado: lida, data_leitura
    - Metadados: created_at, updated_at
    - Display: tipo_display (read-only)
    
    Operações permitidas:
    - Leitura: Todos os campos
    - Escrita: Apenas campo 'lida' (através de métodos específicos)
    """
    
    
    # DISPLAY FIELDS
    
    
    tipo_display = CharField(
        source='get_tipo_display',
        read_only=True,
        help_text=_("Nome legível do tipo de notificação")
    )
    
    
    # COMPUTED FIELDS
    
    
    tempo_desde_criacao = serializers.SerializerMethodField(
        help_text=_("Tempo decorrido desde a criação da notificação")
    )
    
    pode_ser_lida = serializers.SerializerMethodField(
        help_text=_("Indica se a notificação pode ser marcada como lida")
    )
    
    status_leitura = serializers.SerializerMethodField(
        help_text=_("Status detalhado da leitura da notificação")
    )

    
    # META CONFIGURATION
    
    
    class Meta:
        model = Notificacao
        fields = [
            # IDs e relacionamentos
            'id',
            'usuario',
            
            # Dados principais
            'titulo',
            'mensagem',
            'tipo',
            'tipo_display',
            'link',
            
            # Estado de leitura
            'lida',
            'data_leitura',
            'status_leitura',
            
            # Metadados temporais
            'created_at',
            'updated_at',
            'tempo_desde_criacao',
            
            # Permissões
            'pode_ser_lida',
        ]
        
        read_only_fields = [
            # Campos de sistema
            'id',
            'created_at',
            'updated_at',
            
            # Campos de conteúdo (imutáveis após criação)
            'usuario',
            'titulo',
            'mensagem',
            'tipo',
            'link',
            
            # Campos calculados
            'tipo_display',
            'tempo_desde_criacao',
            'pode_ser_lida',
            'status_leitura',
            
            # Data de leitura é gerenciada automaticamente
            'data_leitura',
        ]
        
        extra_kwargs = {
            'lida': {
                'help_text': _("Indica se a notificação foi lida pelo usuário")
            },
        }

    
    # SERIALIZER METHOD FIELDS
    
    
    def get_tempo_desde_criacao(self, obj: Notificacao) -> str:
        """
        Retorna o tempo decorrido desde a criação da notificação.
        
        Args:
            obj: Instância da notificação
            
        Returns:
            String formatada com o tempo decorrido
        """
        if not obj.created_at:
            return _("Data não disponível")
        
        agora = timezone.now()
        delta = agora - obj.created_at
        
        if delta.days > 0:
            return _("há %(days)d dias") % {'days': delta.days}
        elif delta.seconds >= 3600:
            horas = delta.seconds // 3600
            return _("há %(hours)d horas") % {'hours': horas}
        elif delta.seconds >= 60:
            minutos = delta.seconds // 60
            return _("há %(minutes)d minutos") % {'minutes': minutos}
        else:
            return _("há poucos segundos")
    
    def get_pode_ser_lida(self, obj: Notificacao) -> bool:
        """
        Verifica se a notificação pode ser marcada como lida.
        
        Args:
            obj: Instância da notificação
            
        Returns:
            True se pode ser marcada como lida, False caso contrário
        """
        # Notificações já lidas não podem ser marcadas novamente
        if obj.lida:
            return False
        
        # Verifica se o usuário atual é o destinatário
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return obj.usuario == request.user
        
        return True
    
    def get_status_leitura(self, obj: Notificacao) -> Dict[str, Any]:
        """
        Retorna status detalhado da leitura da notificação.
        
        Args:
            obj: Instância da notificação
            
        Returns:
            Dicionário com informações detalhadas do status
        """
        if obj.lida and obj.data_leitura:
            return {
                'status': 'lida',
                'data_leitura': obj.data_leitura,
                'tempo_para_leitura': self._calcular_tempo_para_leitura(obj),
                'lida_em': self._formatar_data_leitura(obj.data_leitura)
            }
        
        return {
            'status': 'nao_lida',
            'data_leitura': None,
            'tempo_para_leitura': None,
            'pendente_desde': self.get_tempo_desde_criacao(obj)
        }

    
    # VALIDATION METHODS
    
    
    def validate_lida(self, value: bool) -> bool:
        """
        Valida o campo 'lida'.
        
        Args:
            value: Valor do campo lida
            
        Returns:
            Valor validado
            
        Raises:
            ValidationError: Se a validação falhar
        """
        instance = getattr(self, 'instance', None)
        
        # Verifica se está tentando desmarcar uma notificação como lida
        # quando ela já foi lida há muito tempo (regra de negócio)
        if instance and instance.lida and not value:
            if instance.data_leitura:
                tempo_desde_leitura = timezone.now() - instance.data_leitura
                if tempo_desde_leitura.days > 7:  # 7 dias
                    raise serializers.ValidationError(
                        _("Não é possível desmarcar notificações lidas há mais de 7 dias.")
                    )
        
        return value

    
    # CRUD METHODS
    
    
    def update(self, instance: Notificacao, validated_data: Dict[str, Any]) -> Notificacao:
        """
        Atualiza uma instância de notificação.
        
        Permite apenas alterações no campo 'lida', utilizando os métodos
        de negócio apropriados para manter a consistência dos dados.
        
        Args:
            instance: Instância atual da notificação
            validated_data: Dados validados para atualização
            
        Returns:
            Instância atualizada da notificação
            
        Raises:
            ValidationError: Se houver tentativa de alterar campos protegidos
        """
        # Verifica se apenas o campo 'lida' está sendo alterado
        campos_permitidos = {'lida'}
        campos_alterados = set(validated_data.keys())
        
        if not campos_alterados.issubset(campos_permitidos):
            campos_nao_permitidos = campos_alterados - campos_permitidos
            raise serializers.ValidationError({
                'non_field_errors': [
                    _("Não é possível alterar os campos: %(fields)s") % {
                        'fields': ', '.join(campos_nao_permitidos)
                    }
                ]
            })
        
        # Processa alteração do campo 'lida'
        if 'lida' in validated_data:
            nova_lida = validated_data['lida']
            
            # Marcando como lida
            if nova_lida and not instance.lida:
                instance.marcar_como_lida()
                self._log_acao_leitura(instance, 'marcada_como_lida')
            
            # Desmarcando como lida
            elif not nova_lida and instance.lida:
                instance.lida = False
                instance.data_leitura = None
                instance.save(update_fields=['lida', 'data_leitura'])
                self._log_acao_leitura(instance, 'desmarcada_como_lida')
        
        return instance

    
    # HELPER METHODS
    
    
    def _calcular_tempo_para_leitura(self, obj: Notificacao) -> Optional[str]:
        """
        Calcula o tempo que levou para a notificação ser lida.
        
        Args:
            obj: Instância da notificação
            
        Returns:
            String com o tempo formatado ou None
        """
        if not (obj.created_at and obj.data_leitura):
            return None
        
        delta = obj.data_leitura - obj.created_at
        
        if delta.days > 0:
            return _("%(days)d dias") % {'days': delta.days}
        elif delta.seconds >= 3600:
            horas = delta.seconds // 3600
            return _("%(hours)d horas") % {'hours': horas}
        elif delta.seconds >= 60:
            minutos = delta.seconds // 60
            return _("%(minutes)d minutos") % {'minutes': minutos}
        else:
            return _("menos de 1 minuto")
    
    def _formatar_data_leitura(self, data_leitura: timezone.datetime) -> str:
        """
        Formata a data de leitura para exibição.
        
        Args:
            data_leitura: Data/hora da leitura
            
        Returns:
            String formatada
        """
        return data_leitura.strftime("%d/%m/%Y às %H:%M")
    
    def _log_acao_leitura(self, instance: Notificacao, acao: str) -> None:
        """
        Registra ações de leitura para auditoria.
        
        Args:
            instance: Instância da notificação
            acao: Tipo de ação realizada
        """
        # Implementar logging se necessário
        # Exemplo: criar um modelo de log de ações
        pass

class NotificacaoListSerializer(BaseModelSerializer):
    """
    Serializer otimizado para listagem de notificações.
    
    Versão simplificada focada em performance para operações de listagem,
    incluindo apenas os campos essenciais e computados mais leves.
    
    Características:
    - Campos reduzidos para melhor performance
    - Todos os campos são read-only
    - Incluí informações de exibição essenciais
    - Otimizado para paginação e filtros
    """
    
    
    # DISPLAY FIELDS
    
    
    tipo_display = CharField(
        source='get_tipo_display',
        read_only=True,
        help_text=_("Nome legível do tipo de notificação")
    )
    
    
    # COMPUTED FIELDS
    
    
    tempo_desde_criacao = serializers.SerializerMethodField()
    
    resumo_mensagem = serializers.SerializerMethodField(
        help_text=_("Resumo da mensagem para listagem")
    )
    
    prioridade_visual = serializers.SerializerMethodField(
        help_text=_("Indicador de prioridade visual")
    )

    
    # META CONFIGURATION
    
    
    class Meta:
        model = Notificacao
        fields = [
            'id',
            'titulo',
            'resumo_mensagem',
            'tipo',
            'tipo_display',
            'lida',
            'data_leitura',
            'link',
            'created_at',
            'tempo_desde_criacao',
            'prioridade_visual',
        ]
        read_only_fields = fields

    
    # SERIALIZER METHOD FIELDS
    
    
    def get_tempo_desde_criacao(self, obj: Notificacao) -> str:
        """Versão simplificada do cálculo de tempo."""
        if not obj.created_at:
            return ""
        
        agora = timezone.now()
        delta = agora - obj.created_at
        
        if delta.days > 0:
            return f"{delta.days}d"
        elif delta.seconds >= 3600:
            horas = delta.seconds // 3600
            return f"{horas}h"
        elif delta.seconds >= 60:
            minutos = delta.seconds // 60
            return f"{minutos}m"
        else:
            return "agora"
    
    def get_resumo_mensagem(self, obj: Notificacao) -> str:
        """
        Retorna um resumo da mensagem para listagem.
        
        Args:
            obj: Instância da notificação
            
        Returns:
            Resumo da mensagem truncado
        """
        if not obj.mensagem:
            return ""
        
        max_length = 100
        if len(obj.mensagem) <= max_length:
            return obj.mensagem
        
        return obj.mensagem[:max_length-3] + "..."
    
    def get_prioridade_visual(self, obj: Notificacao) -> str:
        """
        Retorna indicador de prioridade visual baseado no tipo e estado.
        
        Args:
            obj: Instância da notificação
            
        Returns:
            String indicando a prioridade visual
        """
        if not obj.lida:
            # Mapeia tipos para prioridades visuais
            prioridades = {
                TipoNotificacao.URGENTE: 'alta',
                TipoNotificacao.ALERTA: 'media',
                TipoNotificacao.INFO: 'baixa',
                TipoNotificacao.SUCESSO: 'baixa',
            }
            return prioridades.get(obj.tipo, 'baixa')
        
        return 'lida'

class NotificacaoSummarySerializer(serializers.ModelSerializer):
    """
    Serializer para resumo estatístico de notificações.
    
    Usado para exibir contadores e estatísticas rápidas
    sem carregar dados completos das notificações.
    """
    
    total_nao_lidas = serializers.SerializerMethodField()
    total_por_tipo = serializers.SerializerMethodField()
    
    class Meta:
        model = Notificacao
        fields = [
            'total_nao_lidas',
            'total_por_tipo',
        ]
    
    def get_total_nao_lidas(self, obj) -> int:
        """Retorna total de notificações não lidas."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return Notificacao.objects.filter(
                usuario=request.user,
                lida=False
            ).count()
        return 0
    
    def get_total_por_tipo(self, obj) -> Dict[str, int]:
        """Retorna contagem por tipo de notificação."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            from django.db.models import Count
            
            resultado = Notificacao.objects.filter(
                usuario=request.user,
                lida=False
            ).values('tipo').annotate(
                count=Count('tipo')
            )
            
            return {item['tipo']: item['count'] for item in resultado}
        
        return {}
