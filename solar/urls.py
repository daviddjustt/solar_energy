from django.urls import path, include
from django.contrib import admin
from django.conf import settings
from rest_framework_simplejwt.views import TokenBlacklistView
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter
from solar.users.views import CustomUserViewSet, ActivateAccountView
from solar.documents.views import (
    ProjectViewSet, 
    ProjectDocumentListView,
    ProjectDocumentDetailView,
    ConsumerUnitListView,
    ConsumerUnitDetailView
)

router = DefaultRouter()
router.register("users", CustomUserViewSet)
router.register("projects", ProjectViewSet, basename="project") # Registra o ProjectViewSet

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API Docs - Schema
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    # API Docs - Interface UI
    path('api/v1/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    # Adiciona a rota para /api/docs/ que aponta para o Swagger UI
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='api-docs'),

    path('activate/<str:uuid>/<str:token>', ActivateAccountView.as_view(), name='custom-user-activation'),

    # Endpoints personalizados do Djoser e do Router principal
    path('api/v1/', include(router.urls)), # Inclui todas as rotas registradas pelo router (users, projects)
    path('api/v1/auth/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),
    path('api/v1/auth/', include('djoser.urls.jwt')), # Rotas JWT do Djoser

    # Endpoints para Documentos (aninhados sob o projeto)
    # Note que 'projects/<int:project_pk>/' agora é o prefixo para recursos aninhados
    path('api/v1/projects/<int:project_pk>/documents/', ProjectDocumentListView.as_view(), name='project-document-list-create'),
    path('api/v1/projects/<int:project_pk>/documents/<int:pk>/', ProjectDocumentDetailView.as_view(), name='project-document-detail-update-delete'),

    # Endpoints para Unidades Consumidoras (aninhados sob o projeto)
    path('api/v1/projects/<int:project_pk>/consumer_units/', ConsumerUnitListView.as_view(), name='project-consumer-unit-list-create'),
    path('api/v1/projects/<int:project_pk>/consumer_units/<int:pk>/', ConsumerUnitDetailView.as_view(), name='project-consumer-unit-detail-update-delete'),
]

# Servir arquivos estáticos e de mídia em ambiente de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
