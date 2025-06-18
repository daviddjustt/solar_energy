from django.db.models import Q, Prefetch, Count
from django.utils import timezone
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from arcanosig.oper.models import (
    Operacao,
    Guarnicao,
    GuarnicaoMembro,
    CautelaIndividual,
    ItemCautela,
)
from arcanosig.oper.models.enums import StatusEquipamento
from arcanosig.oper.serializers.operacao_serializers import (
    OperacaoSerializer,
    OperacaoListSerializer,
    GuarnicaoSerializer,
    GuarnicaoListSerializer,
    GuarnicaoMembroSerializer,
    OperacaoRecursivaSerializer,
)
from arcanosig.oper.permissions import IsAdminOrOperationsOrGuarnicaoMember
from arcanosig.oper.utils.helpers import handle_exceptions, optimize_queryset # Assumindo que optimize_queryset existe

class OperacaoViewSet(viewsets.ModelViewSet):
    """
    API para gerenciamento de operações.
    - Admin/superuser e is_operacoes=True: acesso total
    - Demais: só vê operações ativas das guarnições onde participa
    """
    queryset = Operacao.objects.all()
    serializer_class = OperacaoSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['start_date', 'end_date', 'is_active']
    ordering = ['-start_date']
    permission_classes = [IsAuthenticated, IsAdminOrOperationsOrGuarnicaoMember]

    def get_queryset(self):
        qs = super().get_queryset()

        # 1) filtrar por is_active via query param
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            flag = is_active.lower() == 'true'
            qs = qs.filter(is_active=flag)

        # 2) auto‐desativar operações já encerradas
        hoje = timezone.now().date()
        # Usa bulk update para eficiência
        Operacao.objects.filter(end_date__lt=hoje, is_active=True).update(is_active=False)
        # Filtra o queryset atual para refletir as desativações
        qs = qs.filter(Q(is_active=True) | Q(end_date__gte=hoje)) # Mantém ativas ou ainda não encerradas

        # 3) otimização de consultas
        # Note: optimize_queryset precisa lidar com o serializer específico usado por este viewset
        qs = optimize_queryset(qs, self.get_serializer_class())

        # 4) filtragem por permissão de usuário
        user = self.request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
            # Assume related_name 'guarnicoes' de Operacao para Guarnicao
            qs = qs.filter(
                Q(is_active=True),
                Q(guarnicoes__membros=user) | Q(guarnicoes__comandante=user)
            ).distinct()

        return qs

    def get_serializer_class(self):
        # Este viewset usa OperacaoListSerializer para listagem e OperacaoSerializer para detalhe
        return OperacaoListSerializer if self.action == 'list' else OperacaoSerializer

    @handle_exceptions
    def perform_create(self, serializer):
        serializer.save()

    @handle_exceptions
    def perform_update(self, serializer):
        serializer.save()

    @action(detail=True, methods=['get'])
    def guarnicoes(self, request, pk=None):
        oper = self.get_object()
        # Pre-fetch membros para o GuarnicaoListSerializer se necessário
        # Assume related_name 'guarnicoes' de Operacao para Guarnicao
        qs = oper.guarnicoes.all().select_related('comandante', 'veiculo').prefetch_related('membros')
        serializer = GuarnicaoListSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    @handle_exceptions
    def resumo(self, request, pk=None):
        oper = self.get_object()
        # Otimiza consultas para os dados do resumo
        # Busca guarnições e pre-fetch membros e cautelas eficientemente
        # Assume related_name 'guarnicoes' de Operacao para Guarnicao
        guarnicoes_qs = oper.guarnicoes.all().prefetch_related(
            Prefetch(
                'membros', # Assume related_name 'membros' de Guarnicao para GuarnicaoMembro
                queryset=GuarnicaoMembro.objects.prefetch_related(
                    Prefetch(
                        'cautelas', # Assume related_name 'cautelas' de GuarnicaoMembro para CautelaIndividual
                        queryset=CautelaIndividual.objects.select_related('item_cautela')
                    )
                )
            )
        )

        gu_ids = list(guarnicoes_qs.values_list('id', flat=True))
        total_guarnicoes = len(gu_ids) # Ou guarnicoes_qs.count() se não precisar da lista de IDs

        # Calcula contagem de viaturas eficientemente
        viaturas = guarnicoes_qs.exclude(veiculo__isnull=True).count()

        # Calcula contagens de cautelas e equipamentos eficientemente
        # Estas contagens podem ser otimizadas usando agregação se necessário, mas o filtro/count atual está correto
        cautelas = CautelaIndividual.objects.filter(guarnicao__in=gu_ids)
        cautela_ids = list(cautelas.values_list('id', flat=True))

        eq_danificados = ItemCautela.objects.filter(
            cautela__in=cautela_ids,
            status_equipamento__in=[
                StatusEquipamento.DANIFICADO,
                StatusEquipamento.INOPERANTE
            ]
        ).count()

        eq_disponiveis = ItemCautela.objects.filter(
            cautela__in=cautela_ids,
            status_equipamento=StatusEquipamento.EM_CONDICOES,
            data_devolucao__isnull=True
        ).count()

        data = {
            "operacao": {
                "id": oper.id,
                "nome": oper.name,
                "data_inicio": oper.start_date,
                "data_fim": oper.end_date,
                "ativa": oper.is_active
            },
            "estatisticas": {
                "equipamentos_danificados": eq_danificados,
                "equipamentos_cautelados_disponiveis": eq_disponiveis,
                "viaturas_envolvidas": viaturas
            },
            "total_guarnicoes": total_guarnicoes # Usa o total calculado
        }
        return Response(data)


class OperacaoRecursosViewSet(viewsets.ViewSet):
    """
    Retorna a árvore recursiva de uma operação:
    Operacao → Guarnições → Veículos, Policiais, Cautelas → Itens
    """
    permission_classes = [IsAuthenticated, IsAdminOrOperationsOrGuarnicaoMember]
    # Este ViewSet não usa um queryset de modelo diretamente para list/retrieve,
    # então implementamos a lógica de busca nos métodos.

    def list(self, request):
        return self._get_recursos(request,
                                 request.query_params.get('operacao_id'),
                                 request.query_params.get('operacao_name'))

    def retrieve(self, request, pk=None):
        # Para retrieve, o pk é o operacao_id
        return self._get_recursos(request, pk, None)

    @handle_exceptions # Adiciona tratamento de exceção ao método interno
    def _get_recursos(self, request, op_id, op_name):
        if not op_id and not op_name:
            return Response(
                {"detail": "É necessário fornecer operacao_id ou operacao_name"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Constrói o queryset otimizado primeiro
        queryset = Operacao.objects.all()

        # Aplica o prefetching profundo necessário para OperacaoRecursivaSerializer
        # O método get_total_guarnicoes do serializer usa obj.guarnicao_set, então prefetch 'guarnicao_set'
        queryset = queryset.prefetch_related(
            Prefetch(
                'guarnicao_set', # Corresponde ao nome do atributo usado no método do serializer
                queryset=Guarnicao.objects.select_related('veiculo', 'comandante').prefetch_related(
                    Prefetch(
                        'membros', # Assume related_name 'membros' de Guarnicao para GuarnicaoMembro
                        queryset=GuarnicaoMembro.objects.select_related('user').prefetch_related(
                            Prefetch(
                                'cautelas', # Assume related_name 'cautelas' de GuarnicaoMembro para CautelaIndividual
                                queryset=CautelaIndividual.objects.select_related('item_cautela')
                            )
                        )
                    )
                    # 'veiculos' # select_related('veiculo') em Guarnicao geralmente é suficiente
                )
            )
        )

        # Usa get_object_or_404 no queryset otimizado
        filtro = {'id': op_id} if op_id else {'name__iexact': op_name}
        oper = get_object_or_404(queryset, **filtro)

        # Passa o objeto com prefetching para o serializer
        serializer = OperacaoRecursivaSerializer(oper, context={'request': request})

        return Response(serializer.data)


class GuarnicaoViewSet(viewsets.ModelViewSet):
    """
    API para gerenciamento de guarnições.
    Permissões:
    - Administradores e superusuários: acesso total
    - Usuários de operações (is_operacoes=True): acesso total
    - Membros: visualizar apenas guarnições das quais são membros
    """
    queryset = Guarnicao.objects.all()
    serializer_class = GuarnicaoListSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = "__all__"
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    permission_classes = [IsAuthenticated, IsAdminOrOperationsOrGuarnicaoMember]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Otimiza a consulta
        queryset = queryset.select_related('operacao', 'comandante', 'veiculo')

        # Adiciona contagem de membros - Usa annotation para eficiência na listagem
        # Esta annotation é útil se o serializer para listagem usar 'total_membros'
        if self.action == 'list':
            queryset = queryset.annotate(membros_count=Count('membros'))

        # Prefetch relacionamentos necessários pelo serializer específico
        # Se GuarnicaoSerializer ou GuarnicaoListSerializer precisar de detalhes dos membros, prefetch
        if self.action == 'retrieve': # Prefetch membros para visualização de detalhe se necessário
             queryset = queryset.prefetch_related('membros') # Assume related_name 'membros' de Guarnicao para GuarnicaoMembro
        # Considerar se o prefetching de membros é necessário para o serializer de listagem (GuarnicaoListSerializer)

        # Filtragem por operação (opcional)
        operacao_id = self.request.query_params.get('operacao_id')
        if operacao_id:
            queryset = queryset.filter(operacao_id=operacao_id)

        # Filtragem por comandante (opcional)
        comandante_id = self.request.query_params.get('comandante_id')
        if comandante_id:
            queryset = queryset.filter(comandante_id=comandante_id)

        # Se não for admin ou operações, mostrar apenas guarnições onde o usuário é membro ou comandante
        user = self.request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
            # Assume related_name 'membros' de Guarnicao para GuarnicaoMembro
            queryset = queryset.filter(
                Q(membros=user) |
                Q(comandante=user)
            ).distinct()

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return GuarnicaoListSerializer
        elif self.action == 'retrieve':
            return GuarnicaoListSerializer
        return GuarnicaoSerializer

    @handle_exceptions
    def perform_create(self, serializer):
        serializer.save()

    @handle_exceptions
    def perform_update(self, serializer):
        serializer.save()

    @action(detail=True, methods=['get'])
    def membros(self, request, pk=None):
        """Retorna todos os membros da guarnição com informações detalhadas."""
        guarnicao = self.get_object() # get_object usa o queryset do viewset, então o prefetching de get_queryset se aplica
        # Os membros já estão prefetched se a ação for 'retrieve' em get_queryset
        # Se não estiverem prefetched, busca-os aqui:
        # membros = GuarnicaoMembro.objects.filter(guarnicao=guarnicao).select_related(
        #     'user', 'guarnicao', 'guarnicao__operacao'
        # )
        # Se estiverem prefetched, acessa-os diretamente:
        membros = GuarnicaoMembro.objects.filter(guarnicao=guarnicao)

        serializer = GuarnicaoMembroSerializer(membros, many=True, context={'request': request})
        return Response(serializer.data)


class GuarnicaoMembroViewSet(viewsets.ModelViewSet):
    """
    API para gerenciamento de membros de guarnições.
    Permissões:
    - Administradores e superusuários: acesso total
    - Usuários de operações (is_operacoes=True): acesso total
    - Comandantes: gerenciar membros de suas próprias guarnições
    """
    queryset = GuarnicaoMembro.objects.all()
    serializer_class = GuarnicaoMembroSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    permission_classes = [IsAuthenticated, IsAdminOrOperationsOrGuarnicaoMember]

    def get_queryset(self):
        queryset = super().get_queryset()
        # Otimiza a consulta
        queryset = queryset.select_related('guarnicao', 'user', 'guarnicao__operacao')

        # Filtragem por guarnição (opcional)
        guarnicao_id = self.request.query_params.get('guarnicao_id')
        if guarnicao_id:
            queryset = queryset.filter(guarnicao_id=guarnicao_id)

        # Filtragem por usuário (opcional)
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Se não for admin ou operações, mostrar apenas membros de guarnições onde o usuário é comandante
        user = self.request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
            queryset = queryset.filter(
                Q(guarnicao__comandante=user)
            )

        return queryset

    # Método modificado para lidar com dados diretos em vez de usar contexto
    # Isso resolve problemas quando o ID da guarnição vem no body do request
    def create(self, request, *args, **kwargs):
        """
        Cria um novo membro para uma guarnição utilizando diretamente os dados da requisição.
        """
        # O serializer deve lidar com campos obrigatórios como user_id e guarnicao_id
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer) # Isto chama serializer.save()
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
                headers=headers
            )
        except Exception as e:
            # Este bloco catch lida com exceções durante is_valid ou perform_create
            # Se handle_exceptions também estiver em perform_create, pode haver tratamento duplicado
            # Assumindo que handle_exceptions é para erros de banco de dados/save, este bloco captura erros de validação etc.
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    # get_serializer_context removido pois o método create não o utiliza

    @handle_exceptions
    def perform_create(self, serializer):
        # Este método é chamado pelo método create após is_valid()
        serializer.save()

    @handle_exceptions
    def perform_update(self, serializer):
        serializer.save()

    def check_object_permissions(self, request, obj):
        """
        Verificar permissões específicas do objeto.
        Apenas administradores, usuários de operações ou comandantes da guarnição podem manipular membros
        """
        # Verifica as permissões de objeto do DRF primeiro (tratadas por permission_classes)
        super().check_object_permissions(request, obj)

        # Verificação adicional: Se não for admin/operações, deve ser o comandante da guarnição do membro
        user = request.user
        if not (user.is_admin or user.is_superuser or user.is_operacoes):
             # Se o usuário não for o comandante da guarnição deste membro específico
             if obj.guarnicao.comandante != user:
                 self.permission_denied(
                     request,
                     message="Você não tem permissão para manipular este membro de guarnição."
                 )