import uuid

# Django
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q, Prefetch, Count

# Django REST Framework
from rest_framework import (
    viewsets, 
    status, 
    filters, 
    serializers, 
    generics,
)

from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

# Local Apps - Models
from arcanosig.oper.models import (
    CautelaIndividual,
    ItemCautela,
    AceiteCautela,
    StatusAceite,
    StatusEquipamento,
    Operacao
)

# Local Apps - Serializers
from arcanosig.oper.serializers.cautela_serializers import (
    CautelaIndividualSerializer,
    CautelaIndividualListSerializer,
    ItemCautelaSerializer,
    AceiteCautelaSerializer,
    AceiteCautelaConfirmacaoSerializer,
    DevolucaoItemSerializer,
    DevolucaoCautelaSerializer,
)

# Local Apps - Other
from arcanosig.oper.permissions import IsAdminOrOperationsOrGuarnicaoMember
from arcanosig.oper.utils.helpers import handle_exceptions, optimize_queryset
from arcanosig.oper.services.cautela_service import CautelaService
from arcanosig.oper.services.notification_hub import NotificationHub
from arcanosig.users.models import User


# VIEWSETS


class CautelaIndividualViewSet(viewsets.ModelViewSet):
    """
    API para gerenciamento de cautelas individuais.
    
    Permissões:
    - Administradores e superusuários: acesso total
    - Usuários de operações (is_operacoes=True): acesso total
    - Policiais: visualizar apenas suas próprias cautelas
    """
    queryset = CautelaIndividual.objects.all()
    serializer_class = CautelaIndividualSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['policial__name', 'guarnicao__name', 'protocolo_aceite']
    ordering_fields = ['data_entrega', 'created_at', 'aceite_status']
    ordering = ['-data_entrega']
    permission_classes = [IsAuthenticated, IsAdminOrOperationsOrGuarnicaoMember]

    def get_queryset(self):
        """Otimiza e filtra o queryset baseado nos parâmetros e permissões do usuário."""
        queryset = super().get_queryset()
        
        # Otimização da consulta
        queryset = queryset.select_related('policial', 'guarnicao', 'guarnicao__operacao')
        queryset = queryset.prefetch_related(
            Prefetch('itens', queryset=ItemCautela.objects.all().order_by('tipo_equipamento')),
            Prefetch('historico_aceites', queryset=AceiteCautela.objects.all().order_by('-created_at'))
        )

        # Aplicar filtros
        queryset = self._apply_filters(queryset)
        
        # Aplicar permissões
        queryset = self._apply_user_permissions(queryset)
        
        return queryset

    def _apply_filters(self, queryset):
        """Aplica filtros baseados nos query parameters."""
        # Filtro por policial
        policial_id = self.request.query_params.get('policial_id')
        if policial_id:
            queryset = queryset.filter(policial_id=policial_id)

        # Filtro por guarnição
        guarnicao_id = self.request.query_params.get('guarnicao_id')
        if guarnicao_id:
            queryset = queryset.filter(guarnicao_id=guarnicao_id)

        # Filtro por status
        status_param = self.request.query_params.get('status')
        if status_param == 'ativa':
            queryset = queryset.filter(data_devolucao__isnull=True)
        elif status_param == 'devolvida':
            queryset = queryset.filter(data_devolucao__isnull=False)

        # Filtro por aceite
        aceite_status = self.request.query_params.get('aceite_status')
        if aceite_status:
            queryset = queryset.filter(aceite_status=aceite_status)

        return queryset

    def _apply_user_permissions(self, queryset):
        """Aplica filtros de permissão baseados no usuário."""
        user = self.request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
            queryset = queryset.filter(
                Q(policial=user) |
                Q(guarnicao__comandante=user) |
                Q(guarnicao__membros=user)
            ).distinct()
        return queryset

    def get_serializer_class(self):
        """Retorna o serializer apropriado para cada ação."""
        if self.action == 'list':
            return CautelaIndividualListSerializer
        return CautelaIndividualSerializer

    @handle_exceptions
    def perform_create(self, serializer):
        """Cria uma nova cautela usando o serviço centralizado."""
        data = serializer.validated_data
        policial = User.objects.get(id=data.pop('policial_id'))
        guarnicao = data.get('guarnicao')

        success, message, cautela = CautelaService.criar_cautela(
            policial=policial,
            guarnicao=guarnicao
        )
        
        if not success:
            raise ValidationError(message)

        serializer.instance = cautela
        return cautela

    @action(detail=True, methods=['post'])
    @handle_exceptions
    def devolver_completa(self, request, pk=None):
        """Devolve todos os itens de uma cautela de uma vez."""
        serializer = DevolucaoCautelaSerializer(data=request.data)
        if serializer.is_valid():
            observacao = serializer.validated_data.get('observacao', '')
            success, message = CautelaService.devolver_cautela_completa(
                cautela_id=pk,
                user=request.user,
                observacao=observacao
            )
            
            status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            return Response({'detail': message}, status=status_code)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def verificar_devolucao_completa(self, request, pk=None):
        """Verifica se todos os itens de uma cautela foram devolvidos."""
        cautela = self.get_object()
        itens_pendentes = cautela.itens.filter(data_devolucao__isnull=True).count()
        
        return Response({
            'completa': itens_pendentes == 0,
            'itens_pendentes': itens_pendentes
        })

    @action(detail=True, methods=['get'])
    def itens_detalhes(self, request, pk=None):
        """Retorna detalhes resumidos dos itens de uma cautela."""
        cautela = self.get_object()
        
        itens_por_tipo = {}
        itens_por_status = {
            'pendentes': 0,
            'devolvidos': 0,
            'danificados': 0
        }

        for item in cautela.itens.all():
            # Contar por tipo
            tipo = item.get_tipo_equipamento_display()
            itens_por_tipo[tipo] = itens_por_tipo.get(tipo, 0) + 1

            # Contar por status
            if not item.data_devolucao:
                itens_por_status['pendentes'] += 1
            else:
                itens_por_status['devolvidos'] += 1
                if item.status_equipamento != StatusEquipamento.EM_CONDICOES:
                    itens_por_status['danificados'] += 1

        return Response({
            'total_itens': cautela.itens.count(),
            'por_tipo': itens_por_tipo,
            'por_status': itens_por_status
        })

    @action(detail=False, methods=['get'], url_path='por-operacao/(?P<operacao_id>[^/.]+)')
    def por_operacao(self, request, operacao_id=None):
        """
        Retorna todas as cautelas de uma operação específica com estatísticas.
        GET /api/v1/oper/cautelas/por-operacao/{operacao_id}/
        """
        try:
            operacao = get_object_or_404(Operacao, id=operacao_id)
            qs = self._get_cautelas_por_operacao(operacao, request.query_params.get('status'))
            
            # Calcular estatísticas
            estatisticas = self._calcular_estatisticas_operacao(operacao)
            
            serializer = CautelaIndividualListSerializer(qs, many=True)
            
            return Response({
                'operacao': {
                    'id': operacao.id,
                    'nome': operacao.name,
                },
                **estatisticas,
                'cautelas': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {'detail': f'Erro: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _get_cautelas_por_operacao(self, operacao, status_param=None):
        """Filtra cautelas por operação e status."""
        qs = self.get_queryset().filter(guarnicao__operacao=operacao)
        
        if status_param == 'ativa':
            qs = qs.filter(data_devolucao__isnull=True)
        elif status_param == 'devolvida':
            qs = qs.filter(data_devolucao__isnull=False)
            
        return qs

    def _calcular_estatisticas_operacao(self, operacao):
        """Calcula estatísticas para uma operação."""
        return {
            'total_cautelas': CautelaIndividual.objects.filter(guarnicao__operacao=operacao).count(),
            'cautelas_ativas': CautelaIndividual.objects.filter(
                guarnicao__operacao=operacao,
                data_devolucao__isnull=True
            ).count(),
            'aceites_confirmados': AceiteCautela.objects.filter(
                cautela__guarnicao__operacao=operacao,
                status='CONFIRMADO'
            ).count(),
            'aceites_pendentes': AceiteCautela.objects.filter(
                cautela__guarnicao__operacao=operacao,
                status='PENDENTE'
            ).count(),
            'equipamentos_danificados': ItemCautela.objects.filter(
                cautela__guarnicao__operacao=operacao,
                status_equipamento__in=['DANIFICADO', 'INOPERANTE']
            ).count(),
        }


class ItemCautelaViewSet(viewsets.ModelViewSet):
    """
    API para gerenciamento de itens de cautela.
    
    Permissões:
    - Administradores e superusuários: acesso total
    - Usuários de operações (is_operacoes=True): acesso total
    - Policiais: visualizar apenas itens de suas cautelas
    """
    queryset = ItemCautela.objects.all()
    serializer_class = ItemCautelaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['numero_serie', 'observacao', 'cautela__policial__name']
    ordering_fields = ['tipo_equipamento', 'quantidade', 'created_at']
    ordering = ['tipo_equipamento']
    permission_classes = [IsAuthenticated, IsAdminOrOperationsOrGuarnicaoMember]

    def get_queryset(self):
        """Otimiza e filtra o queryset baseado nas permissões do usuário."""
        queryset = super().get_queryset()
        queryset = queryset.select_related('cautela', 'cautela__policial', 'cautela__guarnicao')
        
        # Aplicar filtros
        queryset = self._apply_filters(queryset)
        
        # Aplicar permissões
        queryset = self._apply_user_permissions(queryset)
        
        return queryset

    def _apply_filters(self, queryset):
        """Aplica filtros baseados nos query parameters."""
        cautela_id = self.request.query_params.get('cautela_id')
        if cautela_id:
            queryset = queryset.filter(cautela_id=cautela_id)

        tipo = self.request.query_params.get('tipo_equipamento')
        if tipo:
            queryset = queryset.filter(tipo_equipamento=tipo)

        devolvido = self.request.query_params.get('devolvido')
        if devolvido is not None:
            if devolvido.lower() == 'true':
                queryset = queryset.filter(data_devolucao__isnull=False)
            else:
                queryset = queryset.filter(data_devolucao__isnull=True)

        return queryset

    def _apply_user_permissions(self, queryset):
        """Aplica filtros de permissão baseados no usuário."""
        user = self.request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
            queryset = queryset.filter(
                Q(cautela__policial=user) |
                Q(cautela__guarnicao__comandante=user) |
                Q(cautela__guarnicao__membros=user)
            ).distinct()
        return queryset

    @handle_exceptions
    def perform_create(self, serializer):
        """Criar novo item associado a uma cautela existente."""
        item = serializer.save()
        cautela = item.cautela
        
        if cautela.aceite_status == StatusAceite.CONFIRMADO:
            NotificationHub.emit_event(
                'item_adicionado',
                item=item,
                cautela=cautela
            )

    @action(detail=True, methods=['post'])
    @handle_exceptions
    def devolver(self, request, pk=None):
        """Registra a devolução de um item de cautela."""
        serializer = DevolucaoItemSerializer(data=request.data)
        if serializer.is_valid():
            status_equipamento = serializer.validated_data.get('status_equipamento')
            descricao_danos = serializer.validated_data.get('descricao_danos', '')
            
            success, message = CautelaService.devolver_item(
                item_id=pk,
                user=request.user,
                status=status_equipamento,
                descricao_danos=descricao_danos
            )
            
            status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            return Response({'detail': message}, status=status_code)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    @handle_exceptions
    def relatar_danos(self, request, pk=None):
        """Registra danos em um equipamento já devolvido."""
        serializer = DevolucaoItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        item = self.get_object()
        
        # Verificar se o item foi devolvido
        if not item.data_devolucao:
            return Response(
                {'detail': "Este item ainda não foi devolvido e não pode ter danos reportados."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Registrar os danos
        status_equipamento = serializer.validated_data.get('status_equipamento')
        descricao_danos = serializer.validated_data.get('descricao_danos', '')
        
        old_status = item.status_equipamento
        item.status_equipamento = status_equipamento
        item.descricao_danos = descricao_danos
        item.save()

        # Notificar sobre danos se necessário
        if (old_status == StatusEquipamento.EM_CONDICOES and 
            status_equipamento != StatusEquipamento.EM_CONDICOES):
            NotificationHub.emit_event(
                'item_danificado',
                item=item,
                cautela=item.cautela
            )

        return Response(
            {'detail': "Danos reportados com sucesso."},
            status=status.HTTP_200_OK
        )


class AceiteCautelaViewSet(viewsets.ModelViewSet):
    """
    API para gerenciamento de aceites de cautela.
    
    Permissões:
    - Administradores e superusuários: acesso total
    - Usuários de operações (is_operacoes=True): acesso total
    - Policiais: visualizar e confirmar apenas seus próprios aceites
    """
    queryset = AceiteCautela.objects.all()
    serializer_class = AceiteCautelaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['protocolo', 'cautela__policial__name', 'observacao']
    ordering_fields = ['created_at', 'data_aceite', 'status']
    ordering = ['-created_at']
    lookup_field = 'protocolo'
    permission_classes = [IsAuthenticated, IsAdminOrOperationsOrGuarnicaoMember]

    def get_queryset(self):
        """Otimiza e filtra o queryset baseado nas permissões do usuário."""
        queryset = super().get_queryset()
        queryset = queryset.select_related('cautela', 'cautela__policial', 'cautela__guarnicao')
        
        # Aplicar filtros
        queryset = self._apply_filters(queryset)
        
        # Aplicar permissões
        queryset = self._apply_user_permissions(queryset)
        
        return queryset

    def _apply_filters(self, queryset):
        """Aplica filtros baseados nos query parameters."""
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        cautela_id = self.request.query_params.get('cautela_id')
        if cautela_id:
            queryset = queryset.filter(cautela_id=cautela_id)

        return queryset

    def _apply_user_permissions(self, queryset):
        """Aplica filtros de permissão baseados no usuário."""
        user = self.request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
            queryset = queryset.filter(
                Q(cautela__policial=user) |
                Q(cautela__guarnicao__comandante=user) |
                Q(cautela__guarnicao__membros=user)
            ).distinct()
        return queryset

    @action(detail=True, methods=['post'])
    @handle_exceptions
    def confirmar(self, request, protocolo=None):
        """Confirma o aceite da cautela pelo policial."""
        serializer = AceiteCautelaConfirmacaoSerializer(data=request.data)
        if serializer.is_valid():
            observacao = serializer.validated_data.get('observacao', '')
            
            success, message = CautelaService.processar_aceite(
                protocolo=protocolo,
                usuario=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
                observacao=observacao
            )
            
            status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
            return Response({'detail': message}, status=status_code)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def pendentes_count(self, request):
        """Retorna a contagem de aceites pendentes para o usuário."""
        user = request.user
        count = AceiteCautela.objects.filter(
            cautela__policial=user,
            status=StatusAceite.PENDENTE
        ).count()
        
        return Response({'count': count}, status=status.HTTP_200_OK)



# API VIEWS


class CautelaResumoOperacaoView(APIView):
    """Endpoint para retornar informações agregadas por operação."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Retorna resumo de todas as operações com dados agregados."""
        operacoes = Operacao.objects.annotate(
            equipamentos_danificados=Count(
                'guarnicoes__cautelas__itens',
                filter=Q(guarnicoes__cautelas__itens__status_equipamento__in=['DANIFICADO', 'INOPERANTE'])
            ),
            cautelas_ativas=Count(
                'guarnicoes__cautelas',
                filter=Q(guarnicoes__cautelas__data_devolucao__isnull=True)
            ),
            aceites_confirmados=Count(
                'guarnicoes__cautelas__historico_aceites',
                filter=Q(guarnicoes__cautelas__historico_aceites__status='CONFIRMADO')
            ),
            aceites_pendentes=Count(
                'guarnicoes__cautelas__historico_aceites',
                filter=Q(guarnicoes__cautelas__historico_aceites__status='PENDENTE')
            )
        ).values(
            'id', 'name', 'equipamentos_danificados',
            'cautelas_ativas', 'aceites_confirmados', 'aceites_pendentes'
        )

        # Transformar dados para o formato esperado
        data = [
            {
                "id_operacao": operacao['id'],
                "nome_operacao": operacao['name'],
                "quantidade_equipamentos_danificados": operacao['equipamentos_danificados'],
                "quantidade_cautelas_ativas": operacao['cautelas_ativas'],
                "quantidade_aceites_confirmados": operacao['aceites_confirmados'],
                "quantidade_aceites_pendentes": operacao['aceites_pendentes'],
            }
            for operacao in operacoes
        ]

        serializer = CautelaResumoOperacaoSerializer(data, many=True)
        return Response(serializer.data)


class OperacaoEstatisticasView(APIView):
    """
    Estatísticas detalhadas de uma operação específica.
    GET /api/v1/oper/operacao/{operacao_id}/estatisticas/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, operacao_id):
        """Retorna estatísticas detalhadas de uma operação."""
        try:
            operacao = get_object_or_404(Operacao, id=operacao_id)

            # Estatísticas por guarnição
            guarnicoes_stats = self._get_guarnicoes_stats(operacao)
            
            # Top equipamentos cautelados
            equipamentos_stats = self._get_equipamentos_stats(operacao)

            return Response({
                'operacao': {
                    'id': operacao.id,
                    'nome': operacao.name
                },
                'guarnicoes': list(guarnicoes_stats),
                'equipamentos_mais_cautelados': list(equipamentos_stats),
                'timestamp': timezone.now()
            })
            
        except Exception as e:
            return Response(
                {'detail': f'Erro ao processar estatísticas: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_guarnicoes_stats(self, operacao):
        """Calcula estatísticas por guarnição."""
        return operacao.guarnicoes.annotate(
            total_cautelas=Count('cautelas'),
            cautelas_ativas=Count('cautelas', filter=Q(cautelas__data_devolucao__isnull=True)),
            itens_danificados=Count('cautelas__itens', filter=Q(
                cautelas__itens__status_equipamento__in=['DANIFICADO', 'INOPERANTE']
            ))
        ).values('id', 'name', 'total_cautelas', 'cautelas_ativas', 'itens_danificados')

    def _get_equipamentos_stats(self, operacao):
        """Calcula estatísticas de equipamentos mais cautelados."""
        return ItemCautela.objects.filter(
            cautela__guarnicao__operacao=operacao
        ).values('tipo_equipamento').annotate(
            quantidade=Count('id')
        ).order_by('-quantidade')[:10]


class CautelaListByOperacaoView(generics.ListAPIView):
    """Retorna uma lista de cautelas individuais filtradas por ID da Operação."""
    serializer_class = CautelaIndividualSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra o queryset por operação."""
        operacao_id = self.kwargs['operacao_id']
        return CautelaIndividual.objects.filter(guarnicao__operacao__id=operacao_id)
