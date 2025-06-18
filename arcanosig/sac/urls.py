
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    RelatorioInteligenciaViewSet,
    RelatorioListaViewSet,
    CompartilhamentoAcessoViewSet,
    CompartilhamentoEspecialAcessoView,
    GerarLinkAcessoEspecialView,
)

router = DefaultRouter()
router.register(r'relatorios-inteligencia', RelatorioInteligenciaViewSet, basename='relatorios-inteligencia')
router.register(r'relatorios-lista-simples', RelatorioListaViewSet, basename='relatorios-lista-simples')
router.register(r'compartilhamento', CompartilhamentoAcessoViewSet, basename='compartilhamento')  # Nova rota

urlpatterns = [
    path('', include(router.urls)),
    # Nova rota para acesso especial direto
    path(
        'compartilhamento-especial-pdf/<str:token>/',
        CompartilhamentoEspecialAcessoView.as_view(),
        name='compartilhamento-especial-acesso'
    ),
    path('relatorios/<uuid:relatorio_uuid>/compartilhamento-especial/', GerarLinkAcessoEspecialView.as_view(), name='gerar-link-acesso-especial'),
]
