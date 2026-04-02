import os
import zipfile
from io import BytesIO

from django.shortcuts import get_object_or_404
from django.http import FileResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from solar.users.models import User
from .models import ClientProject, ProjectDocument, ListaDeMateriais, ConsumerUnit
from .serializers import (
    ProjectInfoSerializer,
    ProjectListSerializer,
    DocumentUploadSerializer,
    ConsumerUnitSerializer,
    TecnicoClientProjectSerializer,
    PaymentDocumentSerializer,
    ListaDeMateriaisSerializer
)

class ProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar projetos com filtragem dinâmica por tipo de usuário.
    """
    queryset = ClientProject.objects.all().order_by('-created_at')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    pagination_class = None
    filterset_fields = ['created_by', 'codigoCliente']

    def get_queryset(self):
        # Proteção para o Swagger e usuários não autenticados
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return ClientProject.objects.none()

        user = self.request.user
        if user.is_superuser or user.is_admin or user.is_tecnico:
            return ClientProject.objects.all().order_by('-created_at')
        
        return ClientProject.objects.filter(created_by=user).order_by('-created_at')

    def get_serializer_class(self):
        # Proteção para o Swagger
        if getattr(self, "swagger_fake_view", False):
            return ProjectInfoSerializer

        user = self.request.user
        # Técnicos e Clientes usam visualização restrita para campos financeiros
        if user.is_authenticated and (user.is_tecnico or user.is_cliente):
            return TecnicoClientProjectSerializer
        
        if self.action == 'list':
            return ProjectListSerializer
        
        return ProjectInfoSerializer
    
    @action(detail=False, methods=['get'])
    def meus_projetos(self, request):
        """Endpoint explícito para contornar requisições do Front-end"""
        # Como o get_queryset já filtra por usuário, basta reutilizá-lo
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        # Aqui o projeto está sendo criado, o dono é o usuário logado
        serializer.save(created_by=self.request.user)

    def _check_financial_permission(self, serializer):
        user = self.request.user
        if user.is_authenticated and (user.is_tecnico or user.is_cliente):
            financial_fields = ['tipo_financeiro', 'valor_financeiro', 'parcelas']
            if any(field in serializer.validated_data for field in financial_fields):
                raise PermissionDenied("Você não tem permissão para modificar campos financeiros.")

    def perform_update(self, serializer):
        self._check_financial_permission(serializer)
        serializer.save()

    @action(detail=False, methods=['get'])
    def resumo_financeiro(self, request):
        user = request.user
        if not (user.is_superuser or user.is_admin):
            return Response({
                'message': 'Acesso negado ao resumo financeiro.',
                'total_projetos': self.get_queryset().count()
            }, status=status.HTTP_403_FORBIDDEN)

        projetos = self.get_queryset()
        # Lógica de soma otimizada pode ser feita aqui
        return Response({'status': 'dados calculados'})

    @extend_schema(operation_id="projects_by_email")
    @action(detail=False, methods=['get'], url_path='by_email')
    def by_email(self, request):
        email = request.query_params.get('email')
        if not email:
            return Response({"detail": "Email obrigatório."}, status=400)
        queryset = self.get_queryset().filter(email=email)
        serializer = ProjectListSerializer(queryset, many=True)
        return Response(serializer.data)

# --- Views de Documentos e Unidades com Proteção de project_pk ---

class ProjectDocumentListView(generics.ListCreateAPIView):
    serializer_class = DocumentUploadSerializer
    queryset = ProjectDocument.objects.all().order_by('-created_at')
    pagination_class = None

    def get_queryset(self):
        project_pk = self.kwargs.get('project_pk')
        if getattr(self, "swagger_fake_view", False) or not project_pk:
            return ProjectDocument.objects.none()
        return ProjectDocument.objects.filter(project_id=project_pk).order_by('-created_at')

    # --- ADICIONE ESTE BLOCO (Força Bruta para Retornar Array Puro) ---
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data) # Garante que o retorno é uma lista []
    # ------------------------------------------------------------------

    def perform_create(self, serializer):
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(ClientProject, pk=project_pk)
        serializer.save(project=project)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            project_pk = self.kwargs.get('project_pk')
            context['project'] = get_object_or_404(ClientProject, pk=project_pk)
        return context


class ConsumerUnitListView(generics.ListCreateAPIView):
    serializer_class = ConsumerUnitSerializer
    queryset = ConsumerUnit.objects.all().order_by('id')
    pagination_class = None
    
    def get_queryset(self):
        project_pk = self.kwargs.get('project_pk')
        if getattr(self, "swagger_fake_view", False) or not project_pk:
            return ConsumerUnit.objects.none()
        return ConsumerUnit.objects.filter(project_id=project_pk).order_by('id')

    # --- ADICIONE ESTE BLOCO ---
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    # ---------------------------

    def perform_create(self, serializer):
        project = get_object_or_404(ClientProject, pk=self.kwargs.get('project_pk'))
        serializer.save(project=project)


class ListaDeMateriasListView(generics.ListCreateAPIView):
    serializer_class = ListaDeMateriaisSerializer
    queryset = ListaDeMateriais.objects.all().order_by('id')
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ListaDeMateriais.objects.none()

        project_pk = self.kwargs.get('project_pk')
        if not project_pk:
            return ListaDeMateriais.objects.none()
        
        # O FILTRO CRÍTICO ESTÁ AQUI: Só retorna materiais do projeto da URL
        return ListaDeMateriais.objects.filter(project_id=project_pk).order_by('id')


    # --- ADICIONE ESTE BLOCO ---
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    # ---------------------------

    def perform_create(self, serializer):
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(ClientProject, pk=project_pk)
        serializer.save(project=project)

        
class PaymentDocumentView(generics.RetrieveUpdateAPIView):
    serializer_class = PaymentDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        if getattr(self, "swagger_fake_view", False):
            return None
            
        project_pk = self.kwargs.get('project_pk')
        document_type = self.kwargs.get('document_type')
        user = self.request.user
        
        project = get_object_or_404(ClientProject, pk=project_pk)
        document = get_object_or_404(ProjectDocument, project=project, document_type=document_type)
        
        # Proteção contra AnonymousUser e permissão de cliente
        if user.is_authenticated and user.is_cliente and project.created_by != user:
             raise PermissionDenied("Acesso negado a este documento.")
             
        return document

    @extend_schema(operation_id="payment_document_update")
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(operation_id="payment_document_partial_update")
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)
    
class ProjectDocumentDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.BINARY}, operation_id="download_document")
    def get(self, request, project_pk, document_pk):
        project = get_object_or_404(ClientProject, pk=project_pk)
        document = get_object_or_404(ProjectDocument, pk=document_pk, project=project)
        
        # 1. Checa a permissão
        if not (request.user.is_superuser or request.user.is_admin or request.user.is_tecnico or request.user == project.created_by):
            raise PermissionDenied("Sem permissão para download.")

        # 2. Evita o Erro 500 checando se a referência do arquivo existe
        if not document.arquivo:
            return Response({"error": "O documento não possui um arquivo anexado."}, status=status.HTTP_404_NOT_FOUND)

        file_path = document.arquivo.path

        # 3. Evita o Erro 500 checando se o arquivo físico ainda está no servidor
        if not os.path.exists(file_path):
            return Response({"error": "Arquivo físico não encontrado. Ele pode ter sido apagado do servidor."}, status=status.HTTP_404_NOT_FOUND)

        # 4. Retorna o arquivo para download
        response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        return response

class ProjectDocumentDownloadAllView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.BINARY}, operation_id="download_all_documents")
    def get(self, request, project_pk):
        project = get_object_or_404(ClientProject, pk=project_pk)
        documents = ProjectDocument.objects.filter(project=project)

        # 1. Checa a permissão
        if not (request.user.is_superuser or request.user.is_admin or request.user.is_tecnico or request.user == project.created_by):
            raise PermissionDenied("Sem permissão para baixar os documentos deste projeto.")

        # 2. Valida se existem documentos
        if not documents.exists():
            return Response({"detail": "Nenhum documento encontrado para este projeto."}, status=status.HTTP_404_NOT_FOUND)

        # 3. Cria o ZIP em memória (sem precisar salvar no disco)
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zip_file:
            arquivos_adicionados = 0
            for doc in documents:
                if doc.arquivo and os.path.exists(doc.arquivo.path):
                    # Gera um nome bonito: "cartao_cnpj_arquivo-original.pdf"
                    file_name_in_zip = f"{doc.document_type}_{os.path.basename(doc.arquivo.path)}"
                    zip_file.write(doc.arquivo.path, file_name_in_zip)
                    arquivos_adicionados += 1

        # 4. Se todos os arquivos físicos foram deletados do servidor, avisa o usuário
        if arquivos_adicionados == 0:
             return Response({"detail": "Os arquivos registrados não foram encontrados fisicamente no servidor."}, status=status.HTTP_404_NOT_FOUND)

        # 5. Prepara a resposta para baixar o ZIP
        buffer.seek(0)
        response = FileResponse(buffer, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="projeto_{project.codigoCliente}_documentos.zip"'
        return response