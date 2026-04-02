from django.urls import path, include, re_path
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter
from solar.users.views import CustomUserViewSet, ActivateAccountView, FilteredUserListView, ClientListView
from django.views.static import serve
from solar.documents.views import (
    ProjectViewSet,
    ProjectDocumentListView,
    ConsumerUnitListView,
    ListaDeMateriasListView,
    PaymentDocumentView,
    ProjectDocumentDownloadView,
    ProjectDocumentDownloadAllView

)
from solar.files.views import (
    DocumentUserListCreateView,
    DocumentUserRetrieveUpdateDestroyView,
    DocumentUserDownloadView,
    DocumentUserDownloadAllView,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .users.permissions import AuthenticationThrottle
from rest_framework.decorators import throttle_classes

router = DefaultRouter()
router.register("users", CustomUserViewSet)
router.register("projects", ProjectViewSet, basename="project") # Registra o ProjectViewSet

class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [AuthenticationThrottle]

class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [AuthenticationThrottle]

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

    # Djoser URLs para gerenciamento de usuários (inclui rotas de reset de senha, ativação, etc.)
    # O Djoser já define as URLs para reset_password_confirm, então não precisamos de uma re_path explícita.
    path('api/v1/', include('djoser.urls')),
    path('api/v1/auth/', include('djoser.urls.jwt')), # Endpoints de autenticação JWT

    # Rota de ativação de conta personalizada (fora dos caminhos padrão do Djoser)
    # Certifique-se de que esta rota não entre em conflito com a rota de ativação do Djoser,
    # caso você esteja usando ambas. Se a ativação do Djoser for suficiente, esta pode ser removida.
    path('activate/<str:uuid>/<str:token>', ActivateAccountView.as_view(), name='custom-user-activation'),

    # Inclui todas as rotas registradas pelo router (users, projects)
    # Cuidado: Se CustomUserViewSet sobrepõe funcionalidades de usuário do Djoser,
    # pode haver conflitos. O ideal é que CustomUserViewSet estenda as views do Djoser
    # ou seja configurado para não conflitar com as URLs padrão do Djoser.
    path('api/v1/', include(router.urls)),

    # Endpoints para Documentos (aninhados sob o projeto)
    # Rota para LISTAR e CRIAR documentos
    path('api/v1/projects/<int:project_pk>/documents/', ProjectDocumentListView.as_view({
        'get': 'list', 
        'post': 'create'
    }), name='project-document-list-create'),

    # Rota para ATUALIZAR (PATCH), DELETAR ou VER um documento específico (o que conserta o seu 404!)
    path('api/v1/projects/<int:project_pk>/documents/<int:pk>/', ProjectDocumentListView.as_view({
        'get': 'retrieve', 
        'patch': 'partial_update', 
        'delete': 'destroy'
    }), name='project-document-detail'),

    path('api/v1/projects/<int:project_pk>/lista_materiais/', ListaDeMateriasListView.as_view(), name='project-material_list-list-create'),
    
    path('api/v1/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/projects/<int:project_pk>/<str:document_type>/', PaymentDocumentView.as_view(),name='payment-document-detail'),
     path(
        'users/<uuid:user_pk>/documents/',
        DocumentUserListCreateView.as_view(),
        name='documentuser-list-create'
    ),
    path(
        'users/<uuid:user_pk>/documents/<int:document_pk>/',
        DocumentUserRetrieveUpdateDestroyView.as_view(),
        name='documentuser-detail'
    ),
    path('filter/clients/', ClientListView.as_view(), name='filtered-user-client-list'),
    path('filter/<str:user_type>/', FilteredUserListView.as_view(), name='filtered-user-list'),

    # Views de download dos documentos
    # Usuários :
    path(
        'api/v1/users/<uuid:user_pk>/documents/<int:document_pk>/download/',
        DocumentUserDownloadView.as_view(),
        name='documentuser-download'
    ),
    path(
        'api/v1/users/<uuid:user_pk>/documents/download-all/',
        DocumentUserDownloadAllView.as_view(),
        name='documentuser-download-all'
    ),
    # ✅ NOVAS URLs para Download de Documentos de Projeto
    path(
        'api/v1/projects/<int:project_pk>/documents/<int:document_pk>/download/',
        ProjectDocumentDownloadView.as_view(),
        name='project-document-download'
    ),
    path(
        'api/v1/projects/<int:project_pk>/documents/download-all/',
        ProjectDocumentDownloadAllView.as_view(),
        name='project-document-download-all'
    ),
]

# Servir arquivos estáticos e de mídia em ambiente de desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

else:
    urlpatterns += [
        re_path(
            r'^media/(?P<path>.*)$',
            serve,
            {'document_root': settings.MEDIA_ROOT}
        ),
    ]