from django.contrib.admin import site as admin_site
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

# --- Third-Party Libraries (DRF, JWT & Swagger) ---
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# --- Apps: Users ---
from solar.users.permissions import AuthenticationThrottle
from solar.users.views import (
    ActivateAccountView,
    ClientListView,
    CustomUserViewSet,
    FilteredUserListView,
)

# --- Apps: Documents & Projects ---
from solar.documents.views import (
    ConsumerUnitListView,
    ListaDeMateriasListView,
    PaymentDocumentView,
    ProjectDocumentDownloadAllView,
    ProjectDocumentDownloadView,
    ProjectDocumentListView,
    ProjectExportExcelView,
    ProjectViewSet,
    SolicitarVistoriaView,
    ProjectProtocolViewSet,
    ProjectSpecificProtocolViewSet
)

# --- Apps: Files ---
from solar.files.views import (
    DocumentUserDownloadAllView,
    DocumentUserDownloadView,
    DocumentUserListCreateView,
    DocumentUserRetrieveUpdateDestroyView,
)

from solar.notifications.views import (
    NotificationViewSet, 
    stream_notifications,
)

# ==============================================================================
# CUSTOM MIDDLEWARE / VIEWS OVERRIDES
# ==============================================================================

class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [AuthenticationThrottle]


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [AuthenticationThrottle]


# ==============================================================================
# ROUTERS SETUP
# ==============================================================================

router = DefaultRouter()
router.register(r"users", CustomUserViewSet, basename="users")
router.register(r"projects", ProjectViewSet, basename="project")
router.register(r'notifications', NotificationViewSet, basename='notification')

# ==============================================================================
# URL PATTERNS
# ==============================================================================

urlpatterns = [
    # --------------------------------------------------------------------------
    # CORE & ADMIN
    # --------------------------------------------------------------------------
    path('admin/', admin.site.urls),

    # --------------------------------------------------------------------------
    # API DOCUMENTATION (SPECTACULAR)
    # --------------------------------------------------------------------------
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='api-docs'),

    # --------------------------------------------------------------------------
    # AUTHENTICATION & USER MANAGEMENT (DJOSER / JWT)
    # --------------------------------------------------------------------------
    path('api/v1/', include('djoser.urls')),
    path('api/v1/auth/', include('djoser.urls.jwt')),
    path('api/v1/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('activate/<str:uuid>/<str:token>/', ActivateAccountView.as_view(), name='custom-user-activation'),

    # --------------------------------------------------------------------------
    # USER FILTERS & ROUTER INCLUSION
    # --------------------------------------------------------------------------
    path('filter/clients/', ClientListView.as_view(), name='filter-clients'),
    path('api/v1/filter/<str:user_type>/', FilteredUserListView.as_view(), name='filtered-user-list'),
    path('api/v1/', include(router.urls)),

    # --------------------------------------------------------------------------
    # PROJECTS: GENERAL ACTIONS
    # --------------------------------------------------------------------------
    path('projects/exportar-excel/', ProjectExportExcelView.as_view(), name='project-export-excel'),
    path('api/v1/projects/<int:project_id>/solicitar-vistoria/', SolicitarVistoriaView.as_view(), name='solicitar-vistoria'),

    # --------------------------------------------------------------------------
    # PROJECTS: NESTED RESOURCES (Order Matters!)
    # --------------------------------------------------------------------------
    # 1. Consumer Units
    path('api/v1/projects/<int:project_pk>/consumer_units/', ConsumerUnitListView.as_view(), name='project-consumer-units'),

    # 2. Material Lists
    path('api/v1/projects/<int:project_pk>/lista_materiais/', ListaDeMateriasListView.as_view(), name='project-material_list-list-create'),

    # 3. Project Documents (CRUD)
    path('api/v1/projects/<int:project_pk>/documents/', ProjectDocumentListView.as_view({'get': 'list', 'post': 'create'}), name='project-document-list-create'),
    path('api/v1/projects/<int:project_pk>/documents/<int:pk>/', ProjectDocumentListView.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='project-document-detail'),

    # 4. Project Downloads
    path('api/v1/projects/<int:project_pk>/documents/download-all/', ProjectDocumentDownloadAllView.as_view(), name='project-document-download-all'),
    path('api/v1/projects/<int:project_pk>/documents/<int:document_pk>/download/', ProjectDocumentDownloadView.as_view(), name='project-document-download'),

    # 5. Payments (⚠️ Dynamic trailing path, keep last!)
    path('api/v1/projects/<int:project_pk>/<str:document_type>/', PaymentDocumentView.as_view(), name='payment-document-detail'),
    
    # 6. Protocol
    path('protocols/', ProjectProtocolViewSet.as_view({'get': 'list','post': 'create'}), name='protocol-global-list'),
    path('protocols/<int:pk>/', ProjectProtocolViewSet.as_view({'get': 'retrieve','put': 'update','patch': 'partial_update','delete': 'destroy'}), name='protocol-global-detail'),
    path('projects/<int:project_pk>/protocols/', ProjectSpecificProtocolViewSet.as_view({'get': 'list','post': 'create'}), name='project-protocols-list'),
    path('projects/<int:project_pk>/protocols/<int:pk>/', ProjectSpecificProtocolViewSet.as_view({'get': 'retrieve','put': 'update','patch': 'partial_update','delete': 'destroy'}), name='project-protocols-detail'),

    # --------------------------------------------------------------------------
    # USERS: NESTED RESOURCES
    # --------------------------------------------------------------------------
    path('api/v1/users/<uuid:user_pk>/documents/', DocumentUserListCreateView.as_view(), name='documentuser-list-create'),
    path('api/v1/users/<uuid:user_pk>/documents/<int:document_pk>/', DocumentUserRetrieveUpdateDestroyView.as_view(), name='documentuser-detail'),
    path('api/v1/users/<uuid:user_pk>/documents/download-all/', DocumentUserDownloadAllView.as_view(), name='documentuser-download-all'),
    path('api/v1/users/<uuid:user_pk>/documents/<int:document_pk>/download/', DocumentUserDownloadView.as_view(), name='documentuser-download'),

    # --------------------------------------------------------------------------
    # NOTIFICATIONS : STREAM
    # --------------------------------------------------------------------------
    # Rota para o Front-end escutar em tempo real via Server-Sent Events (SSE)
    path('stream/', stream_notifications, name='notifications-stream'),
    
    # --------------------------------------------------------------------------
    # ÚLTIMAS ROTAS DEVEM SER COLOCADAS AQUI
    # --------------------------------------------------------------------------
    # Inclui as rotas geradas pelo Router (deve ficar por último para não dar conflito)
    path('', include(router.urls)),
]


# ==============================================================================
# STATIC & MEDIA FILES HANDLING
# ==============================================================================

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)