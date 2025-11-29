from rest_framework import generics, status, viewsets, permissions
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from io import BytesIO
from solar.users.models import User
from rest_framework.response import Response
from django.http import FileResponse
from rest_framework.views import APIView

from rest_framework import serializers
import os
import zipfile

from .models import ClientProject, ProjectDocument, ListaDeMateriais, ConsumerUnit
from solar.users.permissions import IsAdminUser
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
    ViewSet para gerenciar projetos.
    Permite criar, listar, recuperar, atualizar e deletar projetos.
    As operações de detalhe (retrieve, update, destroy) usam o 'pk' (ID) do projeto na URL.
    """
    queryset = ClientProject.objects.all().order_by('-created_at')
    permission_classes = [permissions.IsAuthenticated] # ✅ Mantido, mas pode ser customizado
    filter_backends = [DjangoFilterBackend]
    pagination_class = None
    filterset_fields = ['created_by', 'codigoCliente'] # ✅ Mantido para a listagem padrão

    def get_queryset(self):
        """
        Filtra os projetos com base no tipo de usuário usando as novas flags.
        """
        user = self.request.user
        # Superusuários, Administradores e Técnicos veem tudo
        if user.is_superuser or user.is_admin or user.is_tecnico:
            return ClientProject.objects.all().order_by('-created_at')
        # Clientes veem apenas seus próprios projetos
        if user.is_cliente:
            return ClientProject.objects.filter(created_by=user).order_by('-created_at')
        # Para qualquer outro usuário autenticado (que não se encaixe nas categorias acima)
        return ClientProject.objects.filter(created_by=user).order_by('-created_at')

    def get_serializer_class(self):
        """
        Retorna o serializer apropriado baseado no tipo de usuário e na ação.
        """
        user = self.request.user
        # Técnicos e Clientes usam o serializer com campos financeiros read-only
        if user.is_tecnico or user.is_cliente:
            return TecnicoClientProjectSerializer
        # Para outras ações ou usuários, usa serializers específicos
        if self.action == 'list':
            return ProjectListSerializer
        # Se for 'create', 'retrieve', 'update', 'partial_update', 'destroy'
        # ou qualquer outra action não listada acima, usa ProjectSerializer
        return ProjectInfoSerializer

    def perform_update(self, serializer):
        """Verificar permissões antes de atualizar campos financeiros."""
        user = self.request.user
        if user.is_tecnico or user.is_cliente:
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
        """
        # O get_queryset() já filtra por created_by=user para clientes e outros usuários,
        # e retorna todos para staff. Então, basta usar o queryset filtrado.
        projetos = self.get_queryset()
        serializer = self.get_serializer(projetos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def resumo_financeiro(self, request):
        """
        Endpoint para resumo financeiro.
        Apenas administradores podem acessar.
        """
        user = self.request.user
        # Técnicos e Clientes não podem ver resumos financeiros completos
        if user.is_tecnico or user.is_cliente:
            return Response({
                'message': 'Usuários do tipo Técnico ou Cliente não têm permissão para visualizar resumos financeiros completos.',
                'total_projetos': self.get_queryset().count()
            }, status=status.HTTP_403_FORBIDDEN)

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
        Exemplo: GET /api/v1/projects/by_email/?email=cliente@exemplo.com
        """
        email = request.query_params.get('email')
        if not email:
            return Response(
                {"detail": "O parâmetro 'email' é obrigatório na query string."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Validação de formato de e-mail
        try:
            serializers.EmailField().run_validation(email)
        except serializers.ValidationError:
            return Response(
                {"detail": "O email fornecido não é válido."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Filtra os projetos pelo email
        queryset = self.get_queryset().filter(email=email).order_by('-created_at')
        output_serializer = ProjectListSerializer(queryset, many=True)
        return Response(output_serializer.data, status=status.HTTP_200_OK)

    # ✅ NOVO ENDPOINT: BUSCAR POR created_by (GET com query parameter)
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='created_by',
                type=OpenApiTypes.UUID, # ✅ Tipo UUID
                location=OpenApiParameter.QUERY,
                description='UUID do usuário que criou o projeto.',
                required=True,
            ),
        ],
        responses={
            200: ProjectListSerializer(many=True),
            400: {'description': 'Parâmetro inválido ou ausente'},
            404: {'description': 'Usuário não encontrado'}
        }
    )
    @action(detail=False, methods=['get'], url_path='buscar-por-criador')
    def buscar_projetos_por_criador(self, request):
        """
        Busca projetos por 'created_by' (UUID do usuário) como parâmetro de query.
        Retorna os projetos criados por esse usuário.

        Exemplo de URL: /api/v1/projects/buscar-por-criador/?created_by=3fa85f64-5717-4562-b3fc-2c963f66afa6
        """
        created_by_uuid = request.query_params.get('created_by')

        if not created_by_uuid:
            return Response(
                {"detail": "O parâmetro 'created_by' é obrigatório na query string."},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset() # Começa com o queryset base (respeitando permissões)

        try:
            user = get_object_or_404(User, uuid=created_by_uuid)
            queryset = queryset.filter(created_by=user)
        except User.DoesNotExist:
            return Response(
                {"detail": f"Usuário com UUID '{created_by_uuid}' não encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # ✅ ENDPOINT EXISTENTE: BUSCAR POR created_by OU codigoCliente (POST com body)
    @extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'created_by': {
                        'type': 'string', # ✅ CORRIGIDO: Agora é string (UUID)
                        'format': 'uuid', # ✅ ADICIONADO: Formato UUID
                        'description': 'UUID do usuário que criou o projeto'
                    },
                    'codigoCliente': {
                        'type': 'string',
                        'description': 'Código do cliente'
                    }
                },
                'example': {
                    'codigoCliente': 'ABC123'
                }
            }
        },
        responses={
            200: ProjectListSerializer(many=True),
            400: {'description': 'Parâmetros inválidos ou ausentes'}
        }
    )
    @action(detail=False, methods=['get'], url_path='buscar')
    def buscar_projetos(self, request):
        """
        Busca projetos por 'created_by' OU 'codigoCliente' como parâmetros de query.
        Método: GET
        Exemplo: GET /api/v1/projects/buscar/?created_by=3fa85f64-5717-4562-b3fc-2c963f66afa6&codigoCliente=ABC123
        Você pode enviar um ou ambos os parâmetros.
        Se enviar ambos, a busca será por AND (created_by E codigoCliente).
        """
        created_by_uuid = request.query_params.get('created_by')
        codigo_cliente = request.query_params.get('codigoCliente')

        if not created_by_uuid and not codigo_cliente:
            return Response(
                {
                    "detail": "Pelo menos um dos parâmetros é obrigatório: 'created_by' ou 'codigoCliente'.",
                    "exemplo": "GET /api/v1/projects/buscar/?created_by=UUID_DO_USUARIO ou /api/v1/projects/buscar/?codigoCliente=ABC123"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset() # Inicia com o queryset base (respeitando permissões do usuário)
        if codigo_cliente:
            queryset = queryset.filter(codigoCliente__icontains=codigo_cliente) # icontains para busca parcial

        queryset = queryset.order_by('-created_at')

        output_serializer = ProjectListSerializer(queryset, many=True)
        return Response({
            'total_results': queryset.count(),
            'filters_applied': {
                'created_by': created_by_uuid,
                'codigoCliente': codigo_cliente
            },
            'results': output_serializer.data
        }, status=status.HTTP_200_OK)

class ProjectDocumentListView(generics.ListCreateAPIView):
    """
    Lista todos os documentos de um projeto específico ou faz upload de um novo documento.
    O upload de um documento do mesmo tipo para o mesmo projeto irá atualizá-lo.
    """
    serializer_class = DocumentUploadSerializer
    pagination_class = None

    def get_queryset(self):
        """
        Retorna apenas documentos do projeto especificado na URL.
        """
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        return ProjectDocument.objects.filter(project=project).select_related('project').order_by('-created_at')

    def get_serializer_context(self):
        """
        Passa o projeto e o request no contexto do serializer.
        """
        context = super().get_serializer_context()
        project_pk = self.kwargs.get('project_pk')
        if project_pk:
            project = get_object_or_404(ClientProject, pk=project_pk)
            context['project'] = project # ✅ Project é adicionado ao contexto aqui
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        """
        Implementa lógica de update-or-create com validação extra.
        """
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        document_type = request.data.get('document_type')

        if not document_type:
            raise ValidationError({'document_type': ['Este campo é obrigatório.']})

        existing_doc = ProjectDocument.objects.filter(
            project=project,
            document_type=document_type
        ).first()

        if existing_doc:
            serializer = self.get_serializer(
                existing_doc,
                data=request.data,
                partial=False
            )
            serializer.is_valid(raise_exception=True)

            if 'arquivo' in request.FILES:
                serializer.save(
                    status='IN_ANALYSIS',
                    is_approved=False,
                    rejection_reason=None,
                    approved_at=None
                )
            else:
                serializer.save() 

            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            serializer.save() 

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED,
                headers=self.get_success_headers(serializer.data)
            )


# ==============================================================================
# 2. View para Recuperação, Atualização, Deleção e Aprovação (ProjectDocumentDetailView)
#    URL: /api/v1/projects/{project_pk}/documents/{pk}/
# ==============================================================================

class ProjectDocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Recupera, atualiza ou deleta um documento específico de um projeto.
    """
    serializer_class = DocumentUploadSerializer
    pagination_class = None

    def get_queryset(self):
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        return ProjectDocument.objects.filter(project=project).select_related('project').order_by('-created_at')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        project_pk = self.kwargs.get('project_pk')
        if project_pk:
            project = get_object_or_404(ClientProject, pk=project_pk)
            context['project'] = project
        context['request'] = self.request
        return context

    def perform_update(self, serializer):
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)

        if 'arquivo' in self.request.FILES:
            serializer.save(
                project=project,
                status='IN_ANALYSIS',
                is_approved=False,
                rejection_reason=None
            )
        else:
            serializer.save(project=project)

    def perform_destroy(self, instance):
        instance.delete()

# 3. Views para Unidades Consumidoras do Projeto (Aninhadas)
class ConsumerUnitListView(generics.ListCreateAPIView):
    """
    Lista todas as unidades consumidoras de um projeto específico ou cria uma nova.
    """
    serializer_class = ConsumerUnitSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_permissions(self):
        if self.request and self.request.method in ['PUT', 'PATCH', 'DELETE']:
            permission_classes = [IsAdminUser, permissions.IsAuthenticated]
        else:
            # Permissões para operações de leitura (GET)
            permission_classes = [permissions.IsAuthenticated] # Ou a permissão apropriada para GET

        return [permission() for permission in permission_classes]

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
    pagination_class = None
    lookup_url_kwarg = 'pk' # O nome do argumento URL para a PK da unidade consumidora

    def get_permissions(self):
        if self.request and self.request.method in ['PUT', 'PATCH', 'DELETE']:
            permission_classes = [IsAdminUser, permissions.IsAuthenticated]
        else:
            # Permissões para operações de leitura (GET)
            permission_classes = [permissions.IsAuthenticated] # Ou a permissão apropriada para GET

        return [permission() for permission in permission_classes]
    def get_queryset(self):
        # Garante que estamos operando em unidades consumidoras do projeto correto
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        return project.consumer_units.all()
    
# 5 Lista de materiais
class ListaDeMateriasListView(generics.ListCreateAPIView):
    """
    Listagem e criação de listas de materiais para um projeto específico.
    """
    serializer_class = ListaDeMateriaisSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_permissions(self):
        if self.request and self.request.method in ['PUT', 'PATCH', 'DELETE']:
            permission_classes = [IsAdminUser, permissions.IsAuthenticated]
        else:
            # Permissões para operações de leitura (GET)
            permission_classes = [permissions.IsAuthenticated] # Ou a permissão apropriada para GET

        return [permission() for permission in permission_classes]

    def get_queryset(self):
        project_pk = self.kwargs['project_pk']
        return ListaDeMateriais.objects.filter(project__pk=project_pk)
    
    def create(self, request, *args, **kwargs):
        project_pk = self.kwargs['project_pk']
        try:
            project = ClientProject.objects.get(pk=project_pk)
        except ClientProject.DoesNotExist:
            raise ValidationError({"detail": "Projeto não encontrado para o ID fornecido."})
        
        is_many = isinstance(request.data, list) # Permite o envio de vários objetos
        serializer = self.get_serializer(data=request.data, many=is_many) # Se for uma lista, passamos many=True.
        serializer.is_valid(raise_exception=True)

        # Se many=True, o serializer.save() itera sobre a lista e cria cada um.
        # Precisamos injetar o objeto 'project' em cada item antes de salvar.
        if is_many:
            # Para cada item validado, adiciona a referência ao projeto
            for item_data in serializer.validated_data:
                item_data['project'] = project
            self.perform_create(serializer)
        else:
            serializer.save(project=project)

        # Retorna a resposta com os dados criados e status 201 (Created)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()

class ListaDeMateriasDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Recupera, atualiza ou exclui uma unidade consumidora específica de um projeto.
    """
    serializer_class = ListaDeMateriaisSerializer
    pagination_class = None
    lookup_url_kwarg = 'pk'

    def get_permissions(self):
        if self.request and self.request.method in ['PUT', 'PATCH', 'DELETE']:
            permission_classes = [IsAdminUser, permissions.IsAuthenticated]
        else:
            # Permissões para operações de leitura (GET)
            permission_classes = [permissions.IsAuthenticated] # Ou a permissão apropriada para GET

        return [permission() for permission in permission_classes]
    def get_queryset(self):
        project_pk = self.kwargs['project_pk']
        project = get_object_or_404(ClientProject, pk=project_pk)
        return ListaDeMateriais.objects.filter(project__pk=project_pk)


# 6 Views para download de arquivos 

class ProjectDocumentDownloadView(APIView):
    """
    Permite baixar um documento específico de um projeto.
    URL: /api/v1/projects/<int:project_pk>/documents/<int:document_pk>/download/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_pk, document_pk):
        project = get_object_or_404(ClientProject, pk=project_pk)
        document = get_object_or_404(ProjectDocument, pk=document_pk, project=project)

        # Lógica de Permissão:
        # Apenas o criador do projeto, superusuários, administradores ou técnicos podem baixar.
        if not (request.user.is_superuser or request.user.is_admin or request.user.is_tecnico or request.user == project.created_by):
            raise PermissionDenied("Você não tem permissão para baixar este documento do projeto.")

        # Assumindo que 'arquivo' é um FileField/ImageField no seu modelo ProjectDocument
        if not document.arquivo:
            raise("O documento não possui um arquivo anexado.")

        file_path = document.arquivo.path

        if not os.path.exists(file_path):
            raise("Arquivo não encontrado no servidor.")

        response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        return response

class ProjectDocumentDownloadAllView(APIView):
    
    """
    Compacta e baixa todos os documentos de um projeto em um arquivo ZIP.
    URL: /api/v1/projects/<int:project_pk>/documents/download-all/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_pk):
        project = get_object_or_404(ClientProject, pk=project_pk)
        documents = ProjectDocument.objects.filter(project=project)

        # Lógica de Permissão:
        # Apenas o criador do projeto, superusuários, administradores ou técnicos podem baixar todos os documentos.
        if not (request.user.is_superuser or request.user.is_admin or request.user.is_tecnico or request.user == project.created_by):
            raise PermissionDenied("Você não tem permissão para baixar todos os documentos deste projeto.")

        if not documents.exists():
            return Response({"detail": "Nenhum documento encontrado para este projeto."}, status=status.HTTP_404_NOT_FOUND)

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zip_file:
            for doc in documents:
                if doc.arquivo and os.path.exists(doc.arquivo.path):
                    # Adiciona o arquivo ao ZIP. O segundo argumento é o nome dentro do ZIP.
                    # Usamos doc.document_type para evitar nomes duplicados se houver vários arquivos com o mesmo nome base
                    file_name_in_zip = f"{doc.document_type}_{os.path.basename(doc.arquivo.path)}"
                    zip_file.write(doc.arquivo.path, file_name_in_zip)

        buffer.seek(0)
        response = FileResponse(buffer, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{project.codigoCliente}_documents.zip"'
        return response

# Nova view específica para documentos de pagamento
class PaymentDocumentView(generics.RetrieveUpdateAPIView):
    """
    View específica para gerenciar documentos de pagamento (boleto e comprovante)
    """
    serializer_class = PaymentDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        project_pk = self.kwargs['project_pk']
        document_type = self.kwargs['document_type']  # 'boleto' ou 'comprovante_de_pagamento'
        
        project = get_object_or_404(ClientProject, pk=project_pk)
        document = get_object_or_404(
            ProjectDocument, 
            project=project, 
            document_type=document_type
        )
        
        # Verificar permissões de acessos
        user = self.request.user
        if document_type == 'comprovante_de_pagamento':
            if user.is_cliente and project.created_by != user:
                raise PermissionDenied("Você não tem acesso a este comprovante.")
        
        return document
    
    def perform_update(self, serializer):
        user = self.request.user
        document = self.get_object()
        
        if document.document_type == 'boleto':
            if not (user.is_admin or user.is_tecnico or user.is_superuser):
                raise PermissionDenied("Apenas administradores e técnicos podem editar boletos.")
        
        elif document.document_type == 'comprovante_de_pagamento':
            if user.is_cliente and document.project.created_by != user:
                raise PermissionDenied("Você só pode editar comprovante dos seus próprios projetos.")
        
        serializer.save()