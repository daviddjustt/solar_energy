from django.db.models import Q, Count, Sum, Case, When, IntegerField
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from arcanosig.oper.models import Notificacao
from arcanosig.oper.serializers.notificacao_serializers import (
    NotificacaoSerializer,
    NotificacaoListSerializer,
)
from arcanosig.oper.permissions import IsAdminOrOperationsOrGuarnicaoMember
from arcanosig.oper.utils.helpers import handle_exceptions, optimize_queryset
from arcanosig.users.models import User


class NotificacaoViewSet(viewsets.ModelViewSet):
    """
    API para gerenciamento de notificações.
    GET / PATCH somente.
    """
    queryset = Notificacao.objects.all()
    serializer_class = NotificacaoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['titulo', 'mensagem']
    ordering_fields = ['created_at', 'lida', 'data_leitura']
    ordering = ['-created_at']
    http_method_names = ['get', 'patch', 'head', 'options']
    permission_classes = [IsAuthenticated, IsAdminOrOperationsOrGuarnicaoMember]

    def base_qs(self):
        # select_related + otimização genérica
        qs = Notificacao.objects.select_related('usuario')
        qs = optimize_queryset(qs, self.get_serializer_class())
        # se não for staff, filtrar apenas próprias
        if not self.request.user.is_staff:
            qs = qs.filter(usuario=self.request.user)
        return qs

    def get_queryset(self):
        qs = self.base_qs()
        # aplicar filtros de list (search + ordering)
        qs = self.filter_queryset(qs)
        # filtro extra por lida/tipo
        params = self.request.query_params
        if 'lida' in params:
            qs = qs.filter(lida=(params['lida'].lower() == 'true'))
        if 'tipo' in params:
            qs = qs.filter(tipo=params['tipo'])
        return qs

    def get_serializer_class(self):
        if self.action in ('list', 'por_usuario'):
            return NotificacaoListSerializer
        return NotificacaoSerializer

    @action(detail=True, methods=['patch'])
    @handle_exceptions
    def marcar_como_lida(self, request, pk=None):
        notif = self.get_object()
        if notif.lida:
            return Response(
                {'detail': _("Notificação já está marcada como lida.")},
                status=status.HTTP_400_BAD_REQUEST
            )
        notif.lida = True
        notif.data_leitura = timezone.now()
        notif.save(update_fields=['lida', 'data_leitura'])
        return Response(self.get_serializer(notif).data)

    @action(detail=True, methods=['patch'])
    @handle_exceptions
    def marcar_como_nao_lida(self, request, pk=None):
        notif = self.get_object()
        if not notif.lida:
            return Response(
                {'detail': _("Notificação já está marcada como não lida.")},
                status=status.HTTP_400_BAD_REQUEST
            )
        notif.lida = False
        notif.data_leitura = None
        notif.save(update_fields=['lida', 'data_leitura'])
        return Response(self.get_serializer(notif).data)

    @action(detail=False, methods=['patch'])
    @handle_exceptions
    def marcar_todas_como_lidas(self, request):
        base = Notificacao.objects.filter(usuario=request.user, lida=False)
        total = base.count()
        if total:
            base.update(lida=True, data_leitura=timezone.now())
        msg = ngettext(
            '%(cnt)d notificação marcada como lida.',
            '%(cnt)d notificações marcadas como lidas.',
            total
        ) % {'cnt': total}
        return Response({'detail': msg})

    @action(detail=False, methods=['get'])
    def nao_lidas_count(self, request):
        cnt = Notificacao.objects.filter(usuario=request.user, lida=False).count()
        return Response({'count': cnt})

    @action(detail=False, methods=['get'])
    def por_tipo(self, request):
        qs = Notificacao.objects.all() if request.user.is_staff else Notificacao.objects.filter(usuario=request.user)
        stats = (
            qs.values('tipo')
            .annotate(
                total=Count('id'),
                nao_lidas=Sum(
                    Case(When(lida=False, then=1), default=0, output_field=IntegerField())
                )
            )
            .order_by('tipo')
        )
        return Response(stats)

    @action(detail=False, methods=['get'], url_path='por-usuario/(?P<usuario_id>[^/.]+)')
    @handle_exceptions
    def por_usuario(self, request, usuario_id=None):
        if not request.user.is_staff:
            return Response(
                {'detail': _("Você não tem permissão para acessar notificações de outros usuários.")},
                status=status.HTTP_403_FORBIDDEN
            )
        alvo = get_object_or_404(User, pk=usuario_id)
        qs = optimize_queryset(
            Notificacao.objects.filter(usuario=alvo).select_related('usuario'),
            self.get_serializer_class()
        )
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)
