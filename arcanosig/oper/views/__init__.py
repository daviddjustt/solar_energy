from arcanosig.oper.views.operacao_views import (
    OperacaoViewSet,
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
)
from arcanosig.oper.views.notificacao_views import NotificacaoViewSet

__all__ = [
    'OperacaoViewSet',
    'GuarnicaoViewSet',
    'GuarnicaoMembroViewSet',
    'VeiculoViewSet',
    'FotoVeiculoViewSet',
    'AbastecimentoViewSet',
    'CautelaIndividualViewSet',
    'ItemCautelaViewSet',
    'AceiteCautelaViewSet',
    'NotificacaoViewSet',
]
