from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from rest_framework_simplejwt.views import TokenBlacklistView
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from solar.users.views import CustomUserViewSet, ActivateAccountView
from rest_framework.routers import DefaultRouter

# ✅ Correção no router
router = DefaultRouter()
router.register(r'users', CustomUserViewSet, basename='user')

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
    
    # API Endpoints - Client Projects
    path('api/v1/projects/', include('solar.documents.urls')),
    
    # ✅ IMPORTANTE: URL personalizada DEVE vir ANTES das URLs do Djoser
    path('activate/<str:uid>/<str:token>/', ActivateAccountView.as_view(), name='custom-user-activation'),
    
    # ✅ Endpoints personalizados do usuário (seu ViewSet customizado)
    path('api/v1/auth/', include(router.urls)),
    
    # ✅ JWT endpoints
    path('api/v1/auth/jwt/', include('djoser.urls.jwt')),
    
    # ✅ Token blacklist
    path('api/v1/auth/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),
    
    # ✅ Outras URLs do Djoser (com prefixo diferente para evitar conflito)
    path('api/v1/users/', include('djoser.urls')),
]

# Servir arquivos estáticos e de mídia em ambiente de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
