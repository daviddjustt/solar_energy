from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

# --- DRF & Swagger ---
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# --- Apps: Users ---
from solar.users.views import CustomUserViewSet, ActivateAccountView, FilteredUserListView, ClientListView
from .users.permissions import AuthenticationThrottle

# --- Apps: Documents / Projects ---
from solar.documents.views import (
    ProjectViewSet,
    ProjectDocumentListView,
    ConsumerUnitListView,
    ListaDeMateriasListView,
    PaymentDocumentView,
    ProjectDocumentDownloadView,
    ProjectDocumentDownloadAllView
)

# --- Apps: Files ---
from solar.files.views import (
    DocumentUserListCreateView,
    DocumentUserRetrieveUpdateDestroyView,
    DocumentUserDownloadView,
    DocumentUserDownloadAllView,
)

# ==========================================
# CUSTOM VIEWS JWT
# ==========================================
class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [AuthenticationThrottle]

class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [AuthenticationThrottle]

# ==========================================
# ROUTERS GERAIS
# ==========================================
router = DefaultRouter()
router.register(r"users", CustomUserViewSet, basename="users")
router.register(r"projects", ProjectViewSet, basename="project")

# ==========================================
# URL PATTERNS
# ==========================================
urlpatterns = [
    # --- Painel de Controle ---
    path('admin/', admin.site.urls),

    # --- Documentação da API (Swagger UI / Redoc) ---
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='api-docs'),

    # --- Autenticação e Gestão de Usuários ---
    path('api/v1/', include('djoser.urls')),
    path('api/v1/auth/', include('djoser.urls.jwt')),
    path('api/v1/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('activate/<str:uuid>/<str:token>/', ActivateAccountView.as_view(), name='custom-user-activation'),

    # --- Filtros Customizados de Usuários ---
    path('api/v1/filter/clients/', ClientListView.as_view(), name='filtered-user-client-list'),
    path('api/v1/filter/<str:user_type>/', FilteredUserListView.as_view(), name='filtered-user-list'),

    # --- Inclusão do Router Principal (Engloba as rotas base de Users e Projects) ---
    path('api/v1/', include(router.urls)),

    # ==========================================
    # ROTAS ANINHADAS DE PROJETOS (A Ordem Importa!)
    # ==========================================
    # 1. Unidades Consumidoras
    path('api/v1/projects/<int:project_pk>/consumer_units/', ConsumerUnitListView.as_view(), name='project-consumer-units'),

    # 2. Lista de Materiais
    path('api/v1/projects/<int:project_pk>/lista_materiais/', ListaDeMateriasListView.as_view(), name='project-material_list-list-create'),

    # 3. Documentos do Projeto (CRUD)
    path('api/v1/projects/<int:project_pk>/documents/', ProjectDocumentListView.as_view({
        'get': 'list', 
        'post': 'create'
    }), name='project-document-list-create'),

    path('api/v1/projects/<int:project_pk>/documents/<int:pk>/', ProjectDocumentListView.as_view({
        'get': 'retrieve', 
        'patch': 'partial_update', 
        'delete': 'destroy'
    }), name='project-document-detail'),

    # 4. Downloads de Documentos (Projeto)
    path('api/v1/projects/<int:project_pk>/documents/download-all/', ProjectDocumentDownloadAllView.as_view(), name='project-document-download-all'),
    path('api/v1/projects/<int:project_pk>/documents/<int:document_pk>/download/', ProjectDocumentDownloadView.as_view(), name='project-document-download'),

    # 5. Pagamentos (⚠️ Rota Dinâmica '<str:...>' SEMPRE POR ÚLTIMO)
    path('api/v1/projects/<int:project_pk>/<str:document_type>/', PaymentDocumentView.as_view(), name='payment-document-detail'),


    # ==========================================
    # ROTAS ANINHADAS DE DOCUMENTOS DE USUÁRIOS
    # ==========================================
    path('api/v1/users/<uuid:user_pk>/documents/', DocumentUserListCreateView.as_view(), name='documentuser-list-create'),
    path('api/v1/users/<uuid:user_pk>/documents/<int:document_pk>/', DocumentUserRetrieveUpdateDestroyView.as_view(), name='documentuser-detail'),
    
    # Downloads de Documentos (Usuário)
    path('api/v1/users/<uuid:user_pk>/documents/download-all/', DocumentUserDownloadAllView.as_view(), name='documentuser-download-all'),
    path('api/v1/users/<uuid:user_pk>/documents/<int:document_pk>/download/', DocumentUserDownloadView.as_view(), name='documentuser-download'),
]

# ==========================================
# ARQUIVOS ESTÁTICOS / MEDIA FILES
# ==========================================
if settings.DEBUG:
    # Apenas no ambiente de DESENVOLVIMENTO (local) o Django serve os arquivos
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)