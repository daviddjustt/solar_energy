from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from .models import ClientProject, ConsumerUnit, ProjectDocument
from .serializers import (
    ProjectInfoSerializer,
    ProjectListSerializer,
    DocumentUploadSerializer,
    ConsumerUnitSerializer,
    TecnicoClientProjectSerializer,
)
    
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from .models import ClientProject

class ProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar projetos.
    Permite criar, listar, recuperar, atualizar e deletar projetos.
    O campo 'codigoCliente' é esperado no corpo da requisição para operações de criação/atualização.
    As operações de detalhe (retrieve, update, destroy) usam o 'pk' (ID) do projeto na URL.
    """
    queryset = ClientProject.objects.all().order_by('-created_at')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    pagination_class = None
    filterset_fields = ['codigoCliente']

    def get_queryset(self):
        """
        Filtra os projetos com base no tipo de usuário usando as novas flags.
        """
        user = self.request.user
        # Superusuários veem tudo
        if user.is_superuser:
            return ClientProject.objects.all().order_by('-created_at')
        # Administradores (usando a nova flag) também veem tudo, se essa for a intenção
        if user.is_admin: # Nova verificação para administradores
            return ClientProject.objects.all().order_by('-created_at')
        # Técnicos veem todos os projetos
        if user.is_tecnico: # Usando a nova flag
            return ClientProject.objects.all().order_by('-created_at')
        # Clientes veem apenas seus próprios projetos
        if user.is_cliente: # Usando a nova flag
            return ClientProject.objects.filter(created_by=user).order_by('-created_at')
        # Para qualquer outro usuário autenticado, mostramos apenas os projetos que ele criou.
        return ClientProject.objects.filter(created_by=user).order_by('-created_at')

    def get_serializer_class(self):
        """
        Retorna o serializer apropriado baseado no tipo de usuário e na ação, usando as novas flags.
        """
        user = self.request.user
        # Técnicos e Clientes usam o serializer com campos financeiros read-only
        if user.is_tecnico or user.is_cliente: # Usando as novas flags
            return TecnicoClientProjectSerializer
        # Para outros usuários (ex: administradores ou usuários padrão)
        if self.action == 'list':
            return ProjectListSerializer
        return ProjectInfoSerializer

    def perform_update(self, serializer):
        """Verificar permissões antes de atualizar campos financeiros, usando as novas flags."""
        user = self.request.user
        # Verificar se é técnico ou cliente tentando modificar campos financeiros
        if user.is_tecnico or user.is_cliente: # Usando as novas flags
            financial_fields = ['tipo_financeiro', 'valor_financeiro', 'parcelas']
            for field in financial_fields:
                if field in serializer.validated_data:
                    raise PermissionDenied(
                        f"Usuários do tipo Técnico ou Cliente não podem modificar o campo '{field}'. "
                        "Entre em contato com um administrador."
                    )
        serializer.save()
    
    def perform_partial_update(self, serializer):
        """Mesmo controle para updates parciais."""
        self.perform_update(serializer)

    def perform_create(self, serializer):
        """Automaticamente define o usuário logado como criador"""
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def meus_projetos(self, request):
        """
        Endpoint para projetos do usuário logado.
        O queryset já é filtrado por `get_queryset` para Clientes.
        """
        # A lógica de get_queryset já filtra por created_by=request.user para clientes e usuários padrão.
        # Não precisamos de um filtro extra aqui, apenas chamamos get_queryset.
        projetos = self.get_queryset()
        serializer = self.get_serializer(projetos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def resumo_financeiro(self, request):
        """
        Endpoint para resumo financeiro.
        Apenas usuários que não são Técnicos ou Clientes podem acessar o resumo completo, usando as novas flags.
        """
        user = self.request.user
        # Técnicos e Clientes não podem ver resumos financeiros completos
        if user.is_tecnico or user.is_cliente: # Usando as novas flags
            return Response({
                'message': 'Usuários do tipo Técnico ou Cliente não têm permissão para visualizar resumos financeiros completos.',
                'total_projetos': self.get_queryset().count() # Conta projetos que o usuário *pode* ver
            }, status=status.HTTP_403_FORBIDDEN)
        # Para outros usuários (ex: administradores ou superusuários)
        projetos = self.get_queryset()
        total_valor_unico = sum(
            p.valor_financeiro for p in projetos.filter(tipo_financeiro='valor_unico')
        )
        total_mensalidades = sum(
            p.valor_total for p in projetos.filter(tipo_financeiro='mensalidade')
        )
        return Response({
            'total_projetos': projetos.count(),
            'projetos_valor_unico': projetos.filter(tipo_financeiro='valor_unico').count(),
            'projetos_mensalidade': projetos.filter(tipo_financeiro='mensalidade').count(),
            'valor_total_unico': f"R$ {total_valor_unico:,.2f}",
            'valor_total_mensalidades': f"R$ {total_mensalidades:,.2f}",
            'valor_total_geral': f"R$ {(total_valor_unico + total_mensalidades):,.2f}"
        })

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='email',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Email do cliente para filtrar os projetos.',
                required=True,
            ),
        ]
    )
    @action(detail=False, methods=['get'], url_path='by_email')
    def by_email(self, request):
        """
        Retorna todos os ClientProjects relacionados a um email fornecido como parâmetro de query.
        Método: GET
        Exemplo de Requisição: GET /api/v1/projects/by_email/?email=email_do_cliente@exemplo.com
        """
        email = request.query_params.get('email')
        if not email:
            return Response(
                {"detail": "O parâmetro 'email' é obrigatório na query string."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Opcional: Adicionar validação de formato de e-mail
        try:
            from rest_framework import serializers # Importar serializers aqui para usar EmailField
            serializers.EmailField().run_validation(email)
        except serializers.ValidationError:
            return Response(
                {"detail": "O email fornecido não é válido."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Filtra os ClientProjects pelo email fornecido
        # Importante: Este filtro deve respeitar as permissões do usuário logado.
        # Se um Cliente tentar usar este endpoint, ele só verá os projetos dele,
        # mesmo que o email seja de outro usuário.
        queryset = self.get_queryset().filter(email=email).order_by('-created_at')
        
        # Serializa os projetos encontrados usando o ProjectListSerializer
        output_serializer = ProjectListSerializer(queryset, many=True)
        return Response(output_serializer.data, status=status.HTTP_200_OK)



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

