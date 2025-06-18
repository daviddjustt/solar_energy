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
from solar.users.views import CustomUserViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("users", CustomUserViewSet)

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API Docs - Schema
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),

    # API Docs - Interface UI
    path('api/v1/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Endpoints personalizados do Djoser - IMPORTANTE: colocar antes do include do djoser.urls
    path('api/v1/auth/', include(router.urls)),
    path('api/v1/auth/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),

    path('api/v1/auth/', include('djoser.urls.jwt')),
]

# Servir arquivos estáticos e de mídia em ambiente de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
