import os
import zipfile
from io import BytesIO
import openpyxl

from django.shortcuts import get_object_or_404
from django.http import FileResponse, HttpResponse
from django.utils.timezone import localtime
from django.utils import timezone
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

import openpyxl
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import ClientProject
from .permissions import IsAdminOrTechnician # Aquela que criamos no início


class ProjectExportExcelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="export_projects_bulk_excel_v5",
        parameters=[
            OpenApiParameter(
                name="client_uuids",
                type={'type': 'array', 'items': {'type': 'string', 'format': 'uuid'}},
                location=OpenApiParameter.QUERY,
                description="Lista de UUIDs de clientes (filtra por created_by)",
                explode=True
            ),
            OpenApiParameter(
                name="project_ids",
                type={'type': 'array', 'items': {'type': 'integer'}},
                location=OpenApiParameter.QUERY,
                description="Lista de IDs de projetos",
                explode=True
            ),
            OpenApiParameter(
                name="data_1",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Data inicial do projeto (Formato: AAAA-MM-DD)"
            ),
            OpenApiParameter(
                name="data_2",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Data final do projeto (Formato: AAAA-MM-DD)"
            ),
        ],
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request, user_pk=None):
        # 1. Captura dos parâmetros antigos
        client_uuids = request.query_params.getlist('client_uuids')
        if user_pk:
            client_uuids.append(str(user_pk))
            
        project_ids = request.query_params.getlist('project_ids')

        # 2. Captura dos novos parâmetros de data
        data_inicial = request.query_params.get('data_1')
        data_final = request.query_params.get('data_2')

        # 3. Queryset base otimizado
        queryset = ClientProject.objects.all().select_related('created_by')

        # 4. Aplicação dos filtros tradicionais
        if client_uuids:
            queryset = queryset.filter(created_by__uuid__in=client_uuids)
        
        if project_ids:
            queryset = queryset.filter(id__in=project_ids)

        # 5. Aplicação do filtro por intervalo de datas (created_at)
        if data_inicial:
            queryset = queryset.filter(created_at__date__gte=data_inicial)
        if data_final:
            queryset = queryset.filter(created_at__date__lte=data_final)

        # 6. Geração do Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Relatório Solar"
        
        headers = [
            "Titular", 
            "Classe", 
            "Status", 
            "Código do Cliente (Model)",
            "UUID do Cliente", 
            "Data de Ingresso",
            "Data do Projeto"
        ]
        ws.append(headers)

        for p in queryset:
            user_relatado = p.created_by
            
            uuid_cliente = str(user_relatado.uuid) if user_relatado and hasattr(user_relatado, 'uuid') else "N/A"
            
            data_ingresso_user = "N/A"
            if user_relatado:
                data_user = getattr(user_relatado, 'date_joined', getattr(user_relatado, 'created_at', None))
                if data_user:
                    data_ingresso_user = data_user.strftime('%d/%m/%Y')
            
            ws.append([
                getattr(p, 'nomeTitular', "N/A"),
                getattr(p, 'classe', "N/A"),
                p.get_status_display() if hasattr(p, 'get_status_display') else p.status,
                getattr(p, 'codigoCliente', "N/A"),
                uuid_cliente,
                data_ingresso_user,
                p.created_at.strftime('%d/%m/%Y') if p.created_at else "N/A"
            ])

        # 7. Resposta HTTP
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="export_{timestamp}.xlsx"'
        
        wb.save(response)
        return response
    
class ProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar projetos com filtragem dinâmica por tipo de usuário e controle de acesso robusto.
    """
    queryset = ClientProject.objects.all().order_by('-created_at')
    # get_permissions cuidará do detalhamento das permissões, mas o padrão será IsAuthenticated
    filter_backends = [DjangoFilterBackend]
    pagination_class = None
    filterset_fields = ['created_by', 'codigoCliente']

    def get_permissions(self):
        """
        Define as permissões com base na ação.
        Apenas Admins ou Técnicos podem realizar PUT/PATCH em projetos.
        """
        # Se for uma ação de alteração
        if self.action in ['update', 'partial_update']:
            return [permissions.IsAuthenticated()]
            
        return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return ClientProject.objects.none()

        user = self.request.user
        if user.is_superuser or user.is_admin or user.is_tecnico:
            # select_related adicionado para otimizar a exportação do excel que usa o self.get_queryset()
            return ClientProject.objects.select_related('created_by').order_by('-created_at')
        
        return ClientProject.objects.filter(created_by=user).select_related('created_by').order_by('-created_at')

    def get_serializer_class(self):
        if getattr(self, "swagger_fake_view", False):
            return ProjectInfoSerializer

        user = self.request.user
        
        if self.action in ['update', 'partial_update']:
             # Para atualizações, você já tem o 'TecnicoClientProjectSerializer' que trava campos financeiros.
             # Você deve garantir que dentro da classe Meta dele (no serializers.py), 
             # o 'read_only_fields' contém as imagens e unidades geradoras.
             return TecnicoClientProjectSerializer
             
        # Se não for update, segue o fluxo normal de leitura:
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


    # ==========================================
    # BLINDAGEM DE AÇÕES (UPDATE)
    # ==========================================
    def _check_update_permission(self):
        """Verifica se o usuário tem cargo suficiente para editar o projeto."""
        user = self.request.user
        if not (user.is_superuser or user.is_admin or user.is_tecnico):
             raise PermissionDenied("Apenas Administradores e Técnicos podem atualizar projetos.")

    def _check_financial_permission(self, serializer):
        """Bloqueia a alteração de campos financeiros para técnicos."""
        user = self.request.user
        if user.is_authenticated and user.is_tecnico:
            # Confirme os nomes reais dos campos financeiros do seu model aqui:
            financial_fields = ['tipo_financeiro', 'valor_financeiro', 'parcelas']
            if any(field in serializer.validated_data for field in financial_fields):
                raise PermissionDenied("Você não tem permissão para modificar campos financeiros.")

    def update(self, request, *args, **kwargs):
         # O Segurança da Porta
         self._check_update_permission()
         return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
         # O Segurança da Porta
         self._check_update_permission()
         return super().partial_update(request, *args, **kwargs)

    def perform_update(self, serializer):
        # O Segurança das Finanças
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
    
    # ==========================================
    # BLINDAGEM DA ROTA: DELETE /api/v1/projects/{id}/
    # ==========================================
    @extend_schema(operation_id="projects_destroy") # Força o nome exato no Swagger
    def destroy(self, request, *args, **kwargs):
        """
        Intercepta a requisição DELETE. 
        Garante que apenas o Administrador possa apagar projetos.
        """
        user = request.user
        
        # Verifica se o usuário tem a flag de admin ou superuser
        if not (user.is_superuser or user.is_admin):
            raise PermissionDenied("Ação bloqueada: Apenas Administradores podem excluir projetos do sistema.")
            
        # Se passou pela segurança, executa o delete normal
        return super().destroy(request, *args, **kwargs)
    
    @extend_schema(responses={200: OpenApiTypes.BINARY}, operation_id="export_project_excel")
    @action(detail=True, methods=['get'], url_path='exportar-excel-individual')
    def exportar_excel_individual(self, request, pk=None):
        # Renomeei o url_path para evitar conflito com a action da lista
        project = self.get_object()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Dados do Projeto"

        headers = [
            "Titular do Projeto",
            "Classe do Projeto",
            "Status",
            "Código do Cliente",
            "Data de Ingresso do Cliente"
        ]
        ws.append(headers)

        data_ingresso = "Não registrado"
        if project.created_by and project.created_by.created_at:
            data_ingresso = localtime(project.created_by.created_at).strftime('%d/%m/%Y %H:%M')

        row = [
            project.nomeTitular,
            project.classe,
            project.get_status_display(), 
            project.codigoCliente,
            data_ingresso
        ]
        ws.append(row)

        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except:
                    pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column].width = adjusted_width

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        nome_arquivo = f'Projeto_{project.codigoCliente}_Relatorio.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'

        wb.save(response)
        
        return response

    @extend_schema(operation_id="projects_by_email")
    @action(detail=False, methods=['get'], url_path='by_email')
    def by_email(self, request):
        email = request.query_params.get('email')
        if not email:
            return Response({"detail": "Email obrigatório."}, status=400)
        queryset = self.get_queryset().filter(email=email)
        serializer = ProjectListSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @extend_schema(responses={200: OpenApiTypes.BINARY}, operation_id="export_project_excel")
    @action(detail=True, methods=['get'], url_path='exportar-excel')
    def exportar_excel(self, request, pk=None):
        """
        Gera e faz o download de um arquivo Excel (.xlsx) contendo 
        os detalhes específicos do projeto.
        """
        # 1. Recupera o projeto pelo ID (pk) passado na URL
        # O get_object() já garante que o usuário tem permissão para ver este projeto
        project = self.get_object()

        # 2. Cria o arquivo Excel (Workbook) em memória
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Dados do Projeto"

        # 3. Adiciona a linha de Cabeçalhos
        headers = [
            "Titular do Projeto",
            "Classe do Projeto",
            "Status",
            "Código do Cliente",
            "Data de Ingresso do Cliente"
        ]
        ws.append(headers)

        # 4. Extrai a data de ingresso (created_at) da tabela users_user
        # Fazemos um fallback seguro caso o projeto não tenha um criador associado
        data_ingresso = "Não registrado"
        if project.created_by and project.created_by.created_at:
            data_ingresso = localtime(project.created_by.created_at).strftime('%d/%m/%Y %H:%M')

        # 5. Adiciona a linha com os Dados reais
        row = [
            project.nomeTitular,
            project.classe,
            project.get_status_display(), # Usa get_status_display() para pegar "Em Análise" em vez de "IN_ANALYSIS"
            project.codigoCliente,
            data_ingresso
        ]
        ws.append(row)

        # Opcional: Ajustar a largura das colunas para o Excel ficar bonito
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except:
                    pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column].width = adjusted_width

        # 6. Prepara a resposta HTTP informando que é um arquivo de planilha
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        # Configura o nome do arquivo que será baixado
        nome_arquivo = f'Projeto_{project.codigoCliente}_Relatorio.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'

        # 7. Salva o Excel gerado na resposta e retorna
        wb.save(response)
        
        return response


class ProjectDocumentListView(viewsets.ModelViewSet): # Alterado de generics.ListCreateAPIView
    serializer_class = DocumentUploadSerializer
    queryset = ProjectDocument.objects.all().order_by('-created_at')
    pagination_class = None

    def get_queryset(self):
        project_pk = self.kwargs.get('project_pk')
        if getattr(self, "swagger_fake_view", False) or not project_pk:
            return ProjectDocument.objects.none()
        # Filtra documentos pertencentes ao projeto da URL
        return ProjectDocument.objects.filter(project_id=project_pk).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        # Mantém o formato de resposta em array [] esperado pelo front-end
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(ClientProject, pk=project_pk)
        serializer.save(project=project)

    def perform_update(self, serializer):
        # Se o status for alterado para 'APPROVED', registra a data de aprovação
        if serializer.validated_data.get('status') == 'APPROVED':
            from django.utils import timezone
            serializer.save(approved_at=timezone.now())
        else:
            serializer.save()

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
        
        return ListaDeMateriais.objects.filter(project_id=project_pk).order_by('id')

    # --- SOBRESCREVA O MÉTODO CREATE AQUI ---
    def create(self, request, *args, **kwargs):
        # Verifica se o dado enviado é uma lista
        is_many = isinstance(request.data, list)
        
        # Instancia o serializer com many=True se for uma lista
        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(ClientProject, pk=project_pk)
        # O DRF lida automaticamente com o save em massa quando many=True
        serializer.save(project=project)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
     
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