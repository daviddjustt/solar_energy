from django.urls import path, include
from rest_framework.routers import DefaultRouter

from arcanosig.oper.views.operacao_views import (
    OperacaoViewSet,
    OperacaoRecursosViewSet,
    GuarnicaoViewSet,
    GuarnicaoMembroViewSet,
)
from arcanosig.oper.views.veiculo_views import (
    VeiculoViewSet,
    FotoVeiculoViewSet,
    AbastecimentoViewSet,
)
from arcanosig.oper.views.cautela_views import (
    CautelaIndividualViewSet,
    ItemCautelaViewSet,
    AceiteCautelaViewSet,
    CautelaResumoOperacaoView,
    CautelaListByOperacaoView,
)

from arcanosig.oper.views.guarnicao_view import GuarnicaoRemoveMembroView
from arcanosig.oper.views.notificacao_views import NotificacaoViewSet

router = DefaultRouter()
# Operações
router.register(r'operacoes', OperacaoViewSet, basename='operacao')
router.register(r'operacoes-recursos', OperacaoRecursosViewSet, basename='operacoes-recursos')
router.register(r'guarnicoes', GuarnicaoViewSet)
router.register(r'guarnicao-membros', GuarnicaoMembroViewSet)
# Veículos
router.register(r'veiculos', VeiculoViewSet, basename='veiculo')
router.register(r'fotos-veiculos', FotoVeiculoViewSet, basename='foto-veiculo')
router.register(r'abastecimentos', AbastecimentoViewSet, basename='abastecimento')

# Cautelas
router.register(r'cautelas', CautelaIndividualViewSet, basename='cautela')
router.register(r'itens-cautela', ItemCautelaViewSet, basename='item-cautela')
router.register(r'aceites-cautela', AceiteCautelaViewSet, basename='aceite-cautela')

# Notificações
router.register(r'notificacoes', NotificacaoViewSet, basename='notificacao')

app_name = 'oper'
urlpatterns = [
    path('', include(router.urls)),

    # Resumo único de cautelas por operação
    path(
        'cautelas/resumo/',
        CautelaResumoOperacaoView.as_view(),
        name='cautela-resumo'
    ),

    # Remover membro da guarnição
    path('guarnicoes/<int:guarnicao_id>/membros/<uuid:membro_id>/', GuarnicaoRemoveMembroView.as_view(), name='guarnicao-remove-membro'),


    # Listar cautelas de uma operação específica
    path(
        'cautelas/operacao/<int:operacao_id>/',
        CautelaListByOperacaoView.as_view(),
        name='cautela-list-by-operacao'
    ),
]

