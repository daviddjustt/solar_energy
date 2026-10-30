# Single imports
import os
import zipfile
from io import BytesIO
import openpyxl
import logging
import concurrent.futures

# Django imports
import django_filters
from django.shortcuts import get_object_or_404
from django.http import FileResponse, HttpResponse
from django.utils.timezone import localtime
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model

# DRF & Rest imports
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, extend_schema_view
from drf_spectacular.types import OpenApiTypes
from rest_framework import generics, status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.views import APIView

from solar.users.models import User

from .models import (
    ClientProject, 
    ProjectDocument, 
    ListaDeMateriais, 
    ConsumerUnit, 
    ProjectStatusHistory,
    ProjectProtocol,
    AndamentoDoProjeto,
)

from .utils import (
    calcular_regras_potencia_e_valor
)

from .serializers import (
    ProjectListSerializer,
    DocumentUploadSerializer,
    ConsumerUnitSerializer,
    PaymentDocumentSerializer,
    ListaDeMateriaisSerializer,
    ProjectStatusHistorySerializer,
    ProjectProtocolSerializer,
    CoelbaProjectSerializer,
    EnergisaProjectSerializer,
)

from solar.notifications.services import (
    notify_document_rejected,
    notify_document_approved,
    notify_boleto_added,
    notify_comprovante_added,
    notify_project_status_changed,
    notify_protocol_updated,
    notify_inspection_requested,
    notify_new_project_created,
    notify_client_document_uploaded,
)

User = get_user_model()
logger = logging.getLogger(__name__)

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
        client_uuids = request.query_params.getlist('client_uuids')
        if user_pk:
            client_uuids.append(str(user_pk))
            
        project_ids = request.query_params.getlist('project_ids')
        data_inicial = request.query_params.get('data_1')
        data_final = request.query_params.get('data_2')

        queryset = ClientProject.objects.all().select_related('created_by').prefetch_related('material_lists')
        
        if client_uuids:
            queryset = queryset.filter(created_by__uuid__in=client_uuids)
        if project_ids:
            queryset = queryset.filter(id__in=project_ids)
        if data_inicial:
            queryset = queryset.filter(created_at__date__gte=data_inicial)
        if data_final:
            queryset = queryset.filter(created_at__date__lte=data_final)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Relatório Solar"
        
        headers = [
            "Nome do Titular", "Status", "Código do Cliente", 
            "Data de Ingresso", "Criado Por", "Observações",
            "Potência (kW)", "Valor (R$)",
        ]
        ws.append(headers)

        projetos_para_processar = []
        for p in queryset:
            user_relatado = p.created_by
            data_ingresso_user = "N/A"
            criado_por = "N/A"
            if user_relatado:
                data_user = getattr(user_relatado, 'date_joined', getattr(user_relatado, 'created_at', None))
                if data_user:
                    data_ingresso_user = data_user.strftime('%d/%m/%Y')
                criado_por = user_relatado.get_full_name() or getattr(user_relatado, 'email', str(user_relatado))

            total_mod_kw = 0.0
            total_inv_kw = 0.0
            
            for material in p.material_lists.all():
                qtd = float(material.quantidade or 0)
                pot_bruta = float(material.potencia or 0)
                tipo = str(material.tipo or '').lower()
                
                if 'modulo' in tipo or 'módulo' in tipo:
                    # Módulos são EXCLUSIVAMENTE em W. 
                    # Divide-se logo por 1000 para obter kW (kWp).
                    total_mod_kw += (qtd * pot_bruta) / 1000.0
                    
                elif 'inversor' in tipo:
                    # Inversores mantêm a verificação de unidade (podem ser kW ou W)
                    unidade = str(material.unidade_de_medida or '').lower().strip()
                    if 'kw' in unidade:
                        pot_kw = pot_bruta
                    else:
                        pot_kw = pot_bruta / 1000.0
                    
                    total_inv_kw += (qtd * pot_kw)

            projetos_para_processar.append({
                'nome_titular': getattr(p, 'nomeTitular', "N/A"),
                'status_display': p.get_status_display() if hasattr(p, 'get_status_display') else getattr(p, 'status', "N/A"),
                'codigo_cliente': getattr(p, 'codigoCliente', "N/A"),
                'data_ingresso_user': data_ingresso_user,
                'criado_por': criado_por,
                'observacoes': getattr(p, 'observacoes', ""),
                'total_modulos_kw': total_mod_kw,
                'total_inversores_kw': total_inv_kw
            })

        projetos_processados = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            projetos_processados = list(executor.map(calcular_regras_potencia_e_valor, projetos_para_processar))

        for dados in projetos_processados:
            ws.append([
                dados['nome_titular'], dados['status_display'], dados['codigo_cliente'],
                dados['data_ingresso_user'], dados['criado_por'], dados['observacoes'],
                f"{dados['potencia_calculada']:.2f}", f"{dados['valor_calculado']:.2f}"
            ])

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="export_{timestamp}.xlsx"'
        
        wb.save(response)
        return response

class ProjectProtocolViewSet(viewsets.ModelViewSet):
    queryset = ProjectProtocol.objects.all()
    serializer_class = ProjectProtocolSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_tecnico', False):
            return ProjectProtocol.objects.all().order_by('-id')
        return ProjectProtocol.objects.filter(project__created_by=user).order_by('-id')

    def perform_create(self, serializer):
        protocolo = serializer.save()
        notify_protocol_updated(protocolo.project, protocolo.numero_protocolo, protocolo.data_limite)

    def perform_update(self, serializer):
        protocolo = serializer.save()
        notify_protocol_updated(protocolo.project, protocolo.numero_protocolo, protocolo.data_limite)

    def perform_destroy(self, instance):
        instance.delete()

    def _check_staff_permission(self):
        user = self.request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_tecnico', False)):
            raise PermissionDenied("Apenas a equipe técnica pode gerenciar protocolos globais.")

class ProjectSpecificProtocolViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectProtocolSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        project_pk = self.kwargs.get('project_pk')
        queryset = ProjectProtocol.objects.filter(project_id=project_pk)
        
        if not (user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_tecnico', False)):
            queryset = queryset.filter(project__created_by=user)
            
        return queryset.order_by('-id')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(ClientProject, pk=project_pk)
        
        status_metadata = self._calcular_status_atual_e_proximo(project)
        
        return Response({
            'status_atual': status_metadata['atual'],
            'proximo_status': status_metadata['proximo'],
            'protocols': serializer.data
        })

    def perform_create(self, serializer):
        project_pk = self.kwargs.get('project_pk')
        protocolo = serializer.save(project_id=project_pk)
        notify_protocol_updated(protocolo.project, protocolo.numero_protocolo, protocolo.data_limite)

    def perform_update(self, serializer):
        protocolo = serializer.save()
        notify_protocol_updated(protocolo.project, protocolo.numero_protocolo, protocolo.data_limite)

    def _calcular_status_atual_e_proximo(self, project):
        ultimo_historico = ProjectStatusHistory.objects.filter(project=project).first()
        
        esteira_fluxo = [
            AndamentoDoProjeto.ANALISE_DE_DOCUMENTOS.value,
            AndamentoDoProjeto.EXECUCAO.value,
            AndamentoDoProjeto.PAGAMENTO_TRT_ART.value,
            AndamentoDoProjeto.ANALISE_TECNICA.value,
            AndamentoDoProjeto.APROVADO.value,
            AndamentoDoProjeto.VISTORIA.value,
            AndamentoDoProjeto.CONCLUIDO.value
        ]
        
        if not ultimo_historico:
            return {'atual': esteira_fluxo[0], 'proximo': esteira_fluxo[1]}
        
        status_salvo = ultimo_historico.new_status
        status_atual_display = AndamentoDoProjeto.get_display_name(status_salvo) or status_salvo
        
        if status_salvo in ['REPROVADO', AndamentoDoProjeto.REPROVADO.value]:
            return {
                'atual': AndamentoDoProjeto.REPROVADO.value,
                'proximo': "Aguardando correções / Reenvio de documentos"
            }
            
        try:
            index_atual = esteira_fluxo.index(status_atual_display)
            if index_atual + 1 < len(esteira_fluxo):
                proximo_display = esteira_fluxo[index_atual + 1]
            else:
                proximo_display = "Nenhum (Projeto Finalizado)"
                
        except ValueError:
            proximo_display = "Não identificado (Fora do fluxo padrão)"
            
        return {'atual': status_atual_display, 'proximo': proximo_display}

class ClientProjectFilter(django_filters.FilterSet):
    # CharFilter com lookup_expr='iexact' ignora maiúsculas/minúsculas 
    # e contorna a validação estrita do ChoiceFilter original
    grupo = django_filters.CharFilter(field_name='grupo', lookup_expr='iexact')

    class Meta:
        model = ClientProject
        fields = ['created_by', 'codigoCliente', 'grupo']

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = ClientProject.objects.select_related('energisaproject', 'created_by').prefetch_related(
        'documents', 'material_lists', 'consumer_units'
    ).all().order_by('-created_at')

    filter_backends = [DjangoFilterBackend]
    filterset_class = ClientProjectFilter
    pagination_class = None
    
    filterset_class = ClientProjectFilter

    def get_object(self):
        """
        Interceta a requisição de detalhe. Se o projeto estiver marcado 
        como Energisa e possuir a tabela filha, entrega o EnergisaProject (filho) ao DRF,
        impedindo que o serializer receba apenas a casca do ClientProject (pai).
        """
        obj = super().get_object()
        if obj.grupo == 'energisa' and hasattr(obj, 'energisaproject'):
            return obj.energisaproject
        return obj
    
    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        """
        Alternância dinâmica: Lê a requisição e devolve o Serializer correto
        antes de acionar as validações estritas do DRF.
        """
        if getattr(self, "swagger_fake_view", False):
            return CoelbaProjectSerializer
            
        if self.action in ['list', 'meus_projetos']:
            return ProjectListSerializer
            
        grupo = 'coelba'
        
        if self.action in ['create', 'update', 'partial_update']:
            # Na gravação (POST/PUT/PATCH), a intenção no payload (request.data) decide o serializer
            grupo = self.request.data.get('grupo')
            
            # Se for PATCH sem o campo 'grupo' explícito, usamos o que já está salvo no banco
            if not grupo and self.detail:
                grupo = self.get_object().grupo 
                
        elif self.detail:
            # Na leitura (GET detalhe), o campo 'grupo' salvo no banco decide o serializer
            grupo = self.get_object().grupo
            
        if str(grupo).lower() == 'energisa':
            return EnergisaProjectSerializer
            
        return CoelbaProjectSerializer
    
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return ClientProject.objects.none()
        
        user = self.request.user
        base_queryset = ClientProject.objects.select_related('created_by', 'energisaproject').prefetch_related(
            'documents', 'material_lists', 'consumer_units'
        ).order_by('-created_at')

        if user.is_superuser or user.is_admin or user.is_tecnico:
            return base_queryset

        return base_queryset.filter(created_by=user)

    @action(detail=False, methods=['get'])
    def meus_projetos(self, request):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def perform_create(self, serializer):
        projeto = serializer.save(created_by=self.request.user)
        notify_new_project_created(projeto)

    def _check_update_permission(self):
        user = self.request.user
        if not (user.is_superuser or user.is_admin or user.is_tecnico):
             raise PermissionDenied("Apenas Administradores e Técnicos podem atualizar projetos.")

    def _check_financial_permission(self, serializer):
        user = self.request.user
        if user.is_authenticated and user.is_tecnico:
            financial_fields = ['tipo_financeiro', 'valor_financeiro', 'parcelas']
            if any(field in serializer.validated_data for field in financial_fields):
                raise PermissionDenied("Você não tem permissão para modificar campos financeiros.")

    def update(self, request, *args, **kwargs):
         self._check_update_permission()
         return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
         self._check_update_permission()
         return super().partial_update(request, *args, **kwargs)

    def perform_update(self, serializer):
        instance = self.get_object()
        old_status = instance.status
        
        updated_instance = serializer.save()
        new_status = updated_instance.status

        if old_status != new_status:
            ProjectStatusHistory.objects.create(
                project=updated_instance,
                changed_by_uuid=str(self.request.user.uuid),
                old_status=old_status,
                new_status=new_status
            )
            notify_project_status_changed(updated_instance, old_status, new_status)

    @action(detail=True, methods=['get'], url_path='status-history')
    def status_history(self, request, pk=None):
        project = self.get_object()
        history = ProjectStatusHistory.objects.filter(project=project)
        serializer = ProjectStatusHistorySerializer(history, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def resumo_financeiro(self, request):
        user = request.user
        if not (user.is_superuser or user.is_admin):
            return Response({'message': 'Acesso negado ao resumo financeiro.', 'total_projetos': self.get_queryset().count()}, status=status.HTTP_403_FORBIDDEN)
        return Response({'status': 'dados calculados'})

    @extend_schema(operation_id="projects_destroy")
    def destroy(self, request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.is_admin):
            raise PermissionDenied("Ação bloqueada: Apenas Administradores podem excluir projetos do sistema.")
        return super().destroy(request, *args, **kwargs)
    
    @extend_schema(responses={200: OpenApiTypes.BINARY}, operation_id="export_project_excel")
    @action(detail=True, methods=['get'], url_path='exportar-excel')
    def exportar_excel(self, request, pk=None):
        project = get_object_or_404(ClientProject.objects.prefetch_related('material_lists'), pk=pk)
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Dados do Projeto"

        headers = [
            "Titular do Projeto", "Classe do Projeto", "Status", 
            "Código do Cliente", "Data de Ingresso do Cliente",
            "Potência (kW)", "Valor (R$)"
        ]
        ws.append(headers)

        data_ingresso = "Não registrado"
        if project.created_by and project.created_by.created_at:
            data_ingresso = localtime(project.created_by.created_at).strftime('%d/%m/%Y %H:%M')

        total_mod_kw = 0.0
        total_inv_kw = 0.0
        for material in project.material_lists.all():
            qtd = float(material.quantidade or 0)
            pot_bruta = float(material.potencia or 0)
            tipo = str(material.tipo or '').lower()
            
            if 'modulo' in tipo or 'módulo' in tipo:
                # Regra exclusiva: módulos sempre em W
                total_mod_kw += (qtd * pot_bruta) / 1000.0
                
            elif 'inversor' in tipo:
                unidade = str(material.unidade_de_medida or '').lower().strip()
                if 'kw' in unidade:
                    pot_kw = pot_bruta
                else:
                    pot_kw = pot_bruta / 1000.0
                    
                total_inv_kw += (qtd * pot_kw)

        dados_calculados = calcular_regras_potencia_e_valor({
            'total_modulos_kw': total_mod_kw,
            'total_inversores_kw': total_inv_kw
        })

        row = [
            project.nomeTitular, project.classe, project.get_status_display(), 
            project.codigoCliente, data_ingresso,
            f"{dados_calculados['potencia_calculada']:.2f}",
            f"{dados_calculados['valor_calculado']:.2f}"
        ]
        ws.append(row)

        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[column].width = (max_length + 2)

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        nome_arquivo = f'Projeto_{project.codigoCliente}_Relatorio.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
        wb.save(response)
        return response
    
class SolicitarVistoriaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, project_id):
        projeto = get_object_or_404(ClientProject, id=project_id, created_by=request.user)

        try:
            notify_inspection_requested(projeto, request.user)
            projeto.pedido_vistoria = True
            projeto.save()
            return Response({"message": "Vistoria solicitada com sucesso!"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": "Erro ao processar a solicitação de vistoria.", "details": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class AbstractDocumentListViewSet(viewsets.ModelViewSet):
    """
    ViewSet Abstrato para CRUD de documentos associados a uma entidade Pai (Projeto ou Serviço).
    """
    pagination_class = None
    parent_model = None
    parent_url_kwarg = 'parent_pk'

    def get_parent_object(self):
        parent_pk = self.kwargs.get(self.parent_url_kwarg)
        if not parent_pk:
            return None
        return get_object_or_404(self.parent_model, pk=parent_pk)

    def check_read_permission(self, parent):
        raise NotImplementedError("Subclasses devem implementar check_read_permission")

    def check_write_permission(self, parent, document_type=None):
        raise NotImplementedError("Subclasses devem implementar check_write_permission")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.model.objects.none()
            
        parent = self.get_parent_object()
        if not parent:
            return self.model.objects.none()

        self.check_read_permission(parent)
        filter_kwargs = {self.parent_relation_field: parent}
        return self.model.objects.filter(**filter_kwargs).order_by('-created_at')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            parent = self.get_parent_object()
            if parent:
                context['parent'] = parent
        return context

# Gestão de documentos
## Sessão de classes abstratas
class AbstractPaymentDocumentView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    parent_model = None
    parent_url_kwarg = 'parent_pk'  # 👈 Variável dinâmica
    parent_relation_field = None

    def get_object(self):
        if getattr(self, "swagger_fake_view", False):
            return None
        # Busca dinamicamente pelo nome definido na view filha
        parent_pk = self.kwargs.get(self.parent_url_kwarg)
        document_type = self.kwargs.get('document_type')
        
        parent = get_object_or_404(self.parent_model, pk=parent_pk)
        self.check_access_permission(parent)
        
        filter_kwargs = {self.parent_relation_field: parent, 'document_type': document_type}
        return get_object_or_404(self.model, **filter_kwargs)

    def check_access_permission(self, parent):
        raise NotImplementedError()

class AbstractDocumentDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    model = None
    parent_model = None
    parent_url_kwarg = 'parent_pk'     # 👈 Variável dinâmica
    document_url_kwarg = 'document_pk' # 👈 Variável dinâmica

    def check_download_permission(self, request, parent, document):
        raise NotImplementedError()

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    def get(self, request, *args, **kwargs):

        parent_pk = kwargs.get(self.parent_url_kwarg)
        document_pk = kwargs.get(getattr(self, 'document_url_kwarg', 'pk')) 
        parent_obj = get_object_or_404(self.parent_model, pk=parent_pk)

        filter_kwargs = {
            'pk': document_pk,
            self.parent_relation_field: parent_obj  # Ex: 'service': service ou 'project': project
        }

        document = get_object_or_404(self.model, **filter_kwargs)
        self.check_download_permission(request, parent_obj, document)


        if not document.arquivo:
            return Response({"error": "O documento não possui um arquivo anexado."}, status=status.HTTP_404_NOT_FOUND)

        file_path = document.arquivo.path
        if not os.path.exists(file_path):
            return Response({"error": "Arquivo físico não encontrado no servidor."}, status=status.HTTP_404_NOT_FOUND)

        response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        return response


class AbstractDocumentDownloadAllView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    model = None
    parent_model = None
    parent_url_kwarg = 'parent_pk' # 👈 Variável dinâmica
    parent_relation_field = None

    def check_download_all_permission(self, request, parent):
        raise NotImplementedError()

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    def get(self, request, *args, **kwargs): # 👈 Mudança de assinatura aqui
        parent_pk = kwargs.get(self.parent_url_kwarg)
        parent = get_object_or_404(self.parent_model, pk=parent_pk)
        
        self.check_download_all_permission(request, parent)

        filter_kwargs = {self.parent_relation_field: parent}
        documents = self.model.objects.filter(**filter_kwargs)

        if not documents.exists():
            return Response({"detail": "Nenhum documento encontrado."}, status=status.HTTP_404_NOT_FOUND)

        import zipfile
        from io import BytesIO
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zip_file:
            arquivos_adicionados = 0
            for doc in documents:
                if doc.arquivo and os.path.exists(doc.arquivo.path):
                    file_name_in_zip = f"{doc.document_type}_{os.path.basename(doc.arquivo.path)}"
                    zip_file.write(doc.arquivo.path, file_name_in_zip)
                    arquivos_adicionados += 1

        if arquivos_adicionados == 0:
            return Response({"detail": "Arquivos físicos não foram encontrados no servidor."}, status=status.HTTP_404_NOT_FOUND)

        buffer.seek(0)
        response = FileResponse(buffer, content_type='application/zip')
        identifier = getattr(parent, 'codigoCliente', parent.id)
        response['Content-Disposition'] = f'attachment; filename="documentos_{identifier}.zip"'
        return response

## Sesssao de classes concretas
class ProjectDocumentListView(AbstractDocumentListViewSet):
    model = ProjectDocument
    parent_model = ClientProject
    parent_url_kwarg = 'project_pk'
    parent_relation_field = 'project'
    serializer_class = DocumentUploadSerializer

    def check_read_permission(self, project):
        user = self.request.user
        if not (user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_tecnico', False) or user == project.created_by):
            raise PermissionDenied("Sem permissão para visualizar estes documentos.")

    def perform_create(self, serializer):
        project = self.get_parent_object()
        self.check_read_permission(project)
        serializer.save(project=project)

class PaymentDocumentView(AbstractPaymentDocumentView):
    model = ProjectDocument
    parent_model = ClientProject
    parent_url_kwarg = 'project_pk'  # 👈 Adicione isso
    parent_relation_field = 'project'
    serializer_class = PaymentDocumentSerializer

    def check_access_permission(self, project):
        user = self.request.user
        if user.is_authenticated and user.is_cliente and project.created_by != user:
             raise PermissionDenied("Acesso negado a este documento.")

class ProjectDocumentDownloadView(AbstractDocumentDownloadView):
    model = ProjectDocument
    parent_model = ClientProject
    parent_url_kwarg = 'project_pk'     # 👈 Adicione isso
    document_url_kwarg = 'document_pk'  # 👈 Adicione isso

    def check_download_permission(self, request, project, document):
        if not (request.user.is_superuser or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_tecnico', False) or request.user == project.created_by):
            raise PermissionDenied("Sem permissão para download.")

class ProjectDocumentDownloadAllView(AbstractDocumentDownloadAllView):
    model = ProjectDocument
    parent_model = ClientProject
    parent_url_kwarg = 'project_pk'  # 👈 Adicione isso
    parent_relation_field = 'project'

    def check_download_all_permission(self, request, project):
        if not (request.user.is_superuser or getattr(request.user, 'is_admin', False) or getattr(request.user, 'is_tecnico', False) or request.user == project.created_by):
            raise PermissionDenied("Sem permissão para baixar os documentos deste projeto.")
        
# Consumer Units and Material Lists
class ConsumerUnitListView(generics.ListCreateAPIView):
    serializer_class = ConsumerUnitSerializer
    queryset = ConsumerUnit.objects.all().order_by('id')
    pagination_class = None
    
    def get_queryset(self):
        project_pk = self.kwargs.get('project_pk')
        if getattr(self, "swagger_fake_view", False) or not project_pk:
            return ConsumerUnit.objects.none()
        return ConsumerUnit.objects.filter(project_id=project_pk).order_by('id')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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

    def create(self, request, *args, **kwargs):
        is_many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(ClientProject, pk=project_pk)
        serializer.save(project=project)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class ListaDeMateriasDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ListaDeMateriaisSerializer
    
    def get_queryset(self):
        project_pk = self.kwargs.get('project_pk')
        if getattr(self, "swagger_fake_view", False) or not project_pk:
            return ListaDeMateriais.objects.none()
            
        return ListaDeMateriais.objects.filter(project_id=project_pk)
