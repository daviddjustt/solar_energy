from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import ClientProject, ConsumerUnit, ProjectDocument
from .serializers import (
    ProjectInfoSerializer,
    ProjectListSerializer,
    DocumentUploadSerializer,
    ConsumerUnitSerializer
)

# 1. ViewSet para as Informações do Projeto (CRUD completo)
class ProjectViewSet(viewsets.ModelViewSet):
    from django_filters.rest_framework import DjangoFilterBackend
    """
    ViewSet para gerenciar projetos.
    Permite criar, listar, recuperar, atualizar e deletar projetos.
    O campo 'client_code' é esperado no corpo da requisição para operações de criação/atualização.
    As operações de detalhe (retrieve, update, destroy) usam o 'pk' (ID) do projeto na URL.
    """
    queryset = ClientProject.objects.all().order_by('-created_at')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    pagination_class = None
    filterset_fields = ['client_code']
    # Não definimos lookup_field = 'client_code' aqui.
    # Por padrão, o ModelViewSet usa 'pk' para operações de detalhe,
    # o que permite que 'client_code' seja um campo no corpo da requisição.
    

    def get_serializer_class(self):
        """
        Retorna o serializer apropriado dependendo da ação.
        Usa ProjectListSerializer para a ação 'list' (GET em /projects/).
        Usa ProjectInfoSerializer para as demais ações (create, retrieve, update, destroy).
        """
        if self.action == 'list':
            return ProjectListSerializer
        else :
            return ProjectInfoSerializer


# 2. Views para Documentos do Projeto (Aninhadas)
class ProjectDocumentListView(generics.ListCreateAPIView):
    """
    Lista todos os documentos de um projeto específico ou faz upload de um novo documento.
    O upload de um documento do mesmo tipo para o mesmo projeto irá atualizá-lo.
    """
    serializer_class = DocumentUploadSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        # Garante que estamos listando documentos apenas para o projeto especificado na URL
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        return project.documents.all()

    def perform_create(self, serializer):
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        document_type = serializer.validated_data.get('document_type')
        file_obj = serializer.validated_data.get('file')
        description = serializer.validated_data.get('description', '')

        # Verifica se já existe um documento deste tipo para o projeto
        existing_doc = project.documents.filter(document_type=document_type).first()

        if existing_doc:
            # Se existe, atualiza o documento existente (re-upload)
            if file_obj: # Se um novo arquivo foi enviado
                existing_doc.file = file_obj
                existing_doc.description = description
                existing_doc.is_approved = False # Reseta aprovação ao enviar novo arquivo
                existing_doc.rejection_reason = None
                existing_doc.save()
                serializer.instance = existing_doc # Define a instância para a resposta do serializer
            else: # Se não há novo arquivo, apenas atualiza a descrição se necessário
                existing_doc.description = description
                existing_doc.save()
                serializer.instance = existing_doc
        else:
            # Se não existe, cria um novo documento
            serializer.save(project=project)

class ProjectDocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Recupera, atualiza ou exclui um documento específico de um projeto.
    """
    serializer_class = DocumentUploadSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = 'pk' # O nome do argumento URL para a PK do documento

    def get_queryset(self):
        # Garante que estamos operando em documentos do projeto correto
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        return project.documents.all()

    def perform_update(self, serializer):
        # Se um novo arquivo for fornecido durante a atualização, reseta o status de aprovação
        if 'file' in serializer.validated_data:
            serializer.instance.is_approved = False
            serializer.instance.rejection_reason = None
        serializer.save()


# 3. Views para Unidades Consumidoras do Projeto (Aninhadas)
class ConsumerUnitListView(generics.ListCreateAPIView):
    """
    Lista todas as unidades consumidoras de um projeto específico ou cria uma nova.
    """
    serializer_class = ConsumerUnitSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        # Garante que estamos listando unidades consumidoras apenas para o projeto especificado
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        return project.consumer_units.all()

    def perform_create(self, serializer):
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        serializer.save(project=project)

class ConsumerUnitDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Recupera, atualiza ou exclui uma unidade consumidora específica de um projeto.
    """
    serializer_class = ConsumerUnitSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    lookup_url_kwarg = 'pk' # O nome do argumento URL para a PK da unidade consumidora

    def get_queryset(self):
        # Garante que estamos operando em unidades consumidoras do projeto correto
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        return project.consumer_units.all()

