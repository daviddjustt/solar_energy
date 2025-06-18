from django.db.models import Q
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from arcanosig.oper.models import Veiculo, FotoVeiculo, Abastecimento
from arcanosig.oper.serializers.veiculo_serializers import (
    VeiculoSerializer,
    VeiculoListSerializer,
    FotoVeiculoSerializer,
    AbastecimentoSerializer,
    AbastecimentoListSerializer,
)
from arcanosig.oper.permissions import IsAdminOrOperationsOrGuarnicaoMember
from arcanosig.oper.utils.helpers import handle_exceptions, optimize_queryset


class BaseOperacionalViewSet(viewsets.ModelViewSet):
    """
    Base para APIs que precisam:
    - autenticação
    - permissão de admin/operação/guarnição
    - filtro automático por guarnições do usuário
    """
    permission_classes = [IsAuthenticated, IsAdminOrOperationsOrGuarnicaoMember]

    def filter_por_guarnicao(self, queryset, campo_relacionado):
        user = self.request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
            queryset = queryset.filter(
                Q(**{f"{campo_relacionado}__membros": user}) |
                Q(**{f"{campo_relacionado}__comandante": user})
            ).distinct()
        return queryset


class VeiculoViewSet(BaseOperacionalViewSet):
    """
    API para gerenciamento de veículos.
    """
    queryset = Veiculo.objects.all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['placa', 'modelo']
    ordering_fields = ['placa', 'modelo', 'km_atual', 'created_at']
    ordering = ['placa']

    def get_queryset(self):
        qs = super().get_queryset()
        qs = optimize_queryset(qs, self.get_serializer_class())
        return self.filter_por_guarnicao(qs, 'guarnicao_associada')

    def get_serializer_class(self):
        if self.action == 'list':
            return VeiculoListSerializer
        return VeiculoSerializer

    @action(detail=False, methods=['get'], url_path='disponiveis')
    def disponiveis(self, request):
        """
        Lista veículos em condição de uso e sem guarnição associada.
        Aplica todos os filtros e paginação padrão.
        """
        qs = self.get_queryset().filter(em_condicao=True, guarnicao_associada=None)
        qs = self.filter_queryset(qs)
        page = self.paginate_queryset(qs)
        serializer = VeiculoListSerializer(page or qs, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @handle_exceptions
    def perform_create(self, serializer):
        serializer.save()

    @handle_exceptions
    def perform_update(self, serializer):
        serializer.save()


class FotoVeiculoViewSet(BaseOperacionalViewSet):
    """
    API para gerenciamento de fotos de veículos.
    """
    queryset = FotoVeiculo.objects.select_related('veiculo').all()
    serializer_class = FotoVeiculoSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        qs = self.filter_por_guarnicao(qs, 'veiculo__guarnicao_associada')
        veiculo_id = self.request.query_params.get('veiculo_id')
        if veiculo_id:
            qs = qs.filter(veiculo_id=veiculo_id)
        return qs

    @handle_exceptions
    def perform_create(self, serializer):
        serializer.save()

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        user = request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
            ga = getattr(obj.veiculo, 'guarnicao_associada', None)
            membros = getattr(ga, 'membros', None)
            if not (ga and membros and membros.filter(id=user.id).exists()):
                self.permission_denied(request, message="Você não pode manipular fotos deste veículo.")


class AbastecimentoViewSet(BaseOperacionalViewSet):
    """
    API para gerenciamento de abastecimentos.
    """
    queryset = Abastecimento.objects.select_related('veiculo').all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['veiculo__placa', 'observacao']
    ordering_fields = ['data', 'km_atual', 'valor_total']
    ordering = ['-data']

    def get_queryset(self):
        qs = super().get_queryset()
        qs = self.filter_por_guarnicao(qs, 'veiculo__guarnicao_associada')
        veiculo_id = self.request.query_params.get('veiculo_id')
        if veiculo_id:
            qs = qs.filter(veiculo_id=veiculo_id)
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return AbastecimentoListSerializer
        return AbastecimentoSerializer

    @handle_exceptions
    def perform_create(self, serializer):
        inst = serializer.save()
        self._atualiza_km_veiculo(inst)

    @handle_exceptions
    def perform_update(self, serializer):
        inst = serializer.save()
        self._atualiza_km_veiculo(inst)

    def _atualiza_km_veiculo(self, abastecimento):
        veic = abastecimento.veiculo
        if abastecimento.km_atual > veic.km_atual:
            veic.km_atual = abastecimento.km_atual
            veic.save(update_fields=['km_atual'])

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        user = request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
            ga = getattr(obj.veiculo, 'guarnicao_associada', None)
            membros = getattr(ga, 'membros', None)
            if not (ga and membros and membros.filter(id=user.id).exists()):
                self.permission_denied(request, message="Você não pode manipular abastecimentos deste veículo.")
