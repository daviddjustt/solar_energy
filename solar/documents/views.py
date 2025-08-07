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

# 1. Views para as Informações do Projeto (Criação, Leitura, Atualização, Exclusão)
class ClientProjectListView(viewsets.ModelViewSet):

    from rest_framework import viewsets, status
    from rest_framework.response import Response
    from rest_framework.decorators import action

    """
    Lista todos os projetos ou cria um novo projeto.
    Para GET, usa ProjectListSerializer (com contadores).
    Para POST, usa ProjectInfoSerializer (para criação de dados básicos).
    """
    queryset = ClientProject.objects.all()
    permission_classes = [IsAuthenticated]
    lookup_field = 'client_code'

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProjectInfoSerializer # Usa ProjectInfoSerializer para a criação
        return ProjectListSerializer # Usa ProjectListSerializer para a listagem

    def perform_create(self, serializer):
        # Define o usuário que está criando o projeto
        serializer.save(created_by=self.request.user)
    
    def create(self, request, *args, **kwargs):
        client_code_from_url = kwargs.get('client_code')
        client_code_from_url = kwargs.get('created_by')
        if client_code_from_url:
            request.data['client_code'] = client_code_from_url

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(detail=False, methods=['post'], url_path='(?P<client_code>[^/.]+)')
    def create_with_client_code(self, request, client_code=None):
        if not client_code:
            return Response({"detail": "client_code is required in the URL path."}, status=status.HTTP_400_BAD_REQUEST)

        # Adiciona o client_code da URL aos dados da requisição
        # para que o serializer possa processá-lo
        data = request.data.copy()
        data['client_code'] = client_code

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        # Verifica se um projeto com este client_code já existe
        if ClientProject.objects.filter(client_code=client_code).exists():
            return Response({"detail": "Project with this client_code already exists."}, status=status.HTTP_409_CONFLICT)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)



class ClientProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Recupera, atualiza ou exclui um projeto específico.
    Usa ProjectInfoSerializer para todas as operações.
    """
    queryset = ClientProject.objects.all()
    serializer_class = ProjectInfoSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'pk' # O campo de lookup padrão já é 'pk', mas é bom ser explícito

# 2. Views para Documentos do Projeto
class ProjectDocumentListView(generics.ListCreateAPIView):
    """
    Lista todos os documentos de um projeto específico ou faz upload de um novo documento.
    O upload de um documento do mesmo tipo para o mesmo projeto irá atualizá-lo.
    """
    serializer_class = DocumentUploadSerializer
    permission_classes = [IsAuthenticated]

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

# 3. Views para Unidades Consumidoras do Projeto
class ConsumerUnitListView(generics.ListCreateAPIView):
    """
    Lista todas as unidades consumidoras de um projeto específico ou cria uma nova.
    """
    serializer_class = ConsumerUnitSerializer
    permission_classes = [IsAuthenticated]

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
    lookup_url_kwarg = 'pk' # O nome do argumento URL para a PK da unidade consumidora

    def get_queryset(self):
        # Garante que estamos operando em unidades consumidoras do projeto correto
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        return project.consumer_units.all()

