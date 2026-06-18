# Single imports
import os
import zipfile
from io import BytesIO
import openpyxl
import logging
import concurrent.futures

# Django imports
from django.shortcuts import get_object_or_404
from django.http import FileResponse, HttpResponse
from django.utils.timezone import localtime
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model

# DRF & Rest imports
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
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
    calcular_regras_potencia_e_valor,   
)

from .serializers import (
    ProjectInfoSerializer,
    ProjectListSerializer,
    DocumentUploadSerializer,
    ConsumerUnitSerializer,
    TecnicoClientProjectSerializer,
    PaymentDocumentSerializer,
    ListaDeMateriaisSerializer,
    ProjectStatusHistorySerializer,
    ProjectProtocolSerializer
)

from solar.notifications.services import (
    notify_document_rejected,
    notify_document_approved,
    notify_boleto_added,
    notify_comprovante_added,
    notify_project_status_changed,
    notify_protocol_updated,
    notify_inspection_requested,
    notify_new_project_created
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

        # 3. Query para itens 
        queryset = ClientProject.objects.all().select_related('created_by').prefetch_related('material_lists')
        
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
            "Nome do Titular", 
            "Status", 
            "Código do Cliente", 
            "Data de Ingresso",
            "Criado Por",
            "Observações",
            "Potência (kW)",
            "Valor (R$)",
        ]
        ws.append(headers)

        # 7. EXTRAÇÃO E AGREGAÇÃO (Varrendo a ListaDeMateriais)
        projetos_para_processar = []
        for p in queryset:
            # Info do Usuário
            user_relatado = p.created_by
            data_ingresso_user = "N/A"
            criado_por = "N/A"
            if user_relatado:
                data_user = getattr(user_relatado, 'date_joined', getattr(user_relatado, 'created_at', None))
                if data_user:
                    data_ingresso_user = data_user.strftime('%d/%m/%Y')
                criado_por = user_relatado.get_full_name() or getattr(user_relatado, 'email', str(user_relatado))

            # 🟢 SOMA DOS MATERIAIS DO PROJETO
            total_mod_kw = 0.0
            total_inv_kw = 0.0
            
            # O .all() aqui não atinge o banco graças ao prefetch_related
            for material in p.material_lists.all():
                qtd = float(material.quantidade or 0)
                pot_bruta = float(material.potencia or 0)
                tipo = str(material.tipo or '').lower()
                unidade = str(material.unidade_de_medida or '').lower().strip()
                
                # 🟢 NORMALIZAÇÃO DE UNIDADE: Garante que tudo vire kW antes da conta
                if 'kw' in unidade:
                    pot_kw = pot_bruta  # Já está em kW, mantém o valor puro
                else:
                    # Se for 'wats', 'w' ou o padrão do banco, divide por 1000 para virar kW
                    pot_kw = pot_bruta / 1000.0
                
                total_linha_kw = qtd * pot_kw
                
                if 'modulo' in tipo or 'módulo' in tipo:
                    total_mod_kw += total_linha_kw
                elif 'inversor' in tipo:
                    total_inv_kw += total_linha_kw

            # Monta o pacote pro paralelismo
            projetos_para_processar.append({
                'nome_titular': getattr(p, 'nomeTitular', "N/A"),
                'status_display': p.get_status_display() if hasattr(p, 'get_status_display') else getattr(p, 'status', "N/A"),
                'codigo_cliente': getattr(p, 'codigoCliente', "N/A"),
                'data_ingresso_user': data_ingresso_user,
                'criado_por': criado_por,
                'observacoes': getattr(p, 'observacoes', ""),
                
                # Envia os totais já somados e convertidos para kW
                'total_modulos_kw': total_mod_kw,
                'total_inversores_kw': total_inv_kw
            })

        # 8. CÁLCULO PARALELO (Mágica da velocidade)
        projetos_processados = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            projetos_processados = list(executor.map(calcular_regras_potencia_e_valor, projetos_para_processar))

        # 9. ESCREVER NO EXCEL
        for dados in projetos_processados:
            ws.append([
                dados['nome_titular'],
                dados['status_display'],
                dados['codigo_cliente'],
                dados['data_ingresso_user'],
                dados['criado_por'],
                dados['observacoes'],
                f"{dados['potencia_calculada']:.2f}",
                f"{dados['valor_calculado']:.2f}"
            ])

        # 10. Resposta HTTP
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="export_{timestamp}.xlsx"'
        
        wb.save(response)
        return response

class ProjectProtocolViewSet(viewsets.ModelViewSet):
    queryset = ProjectProtocol.objects.all()
    serializer_class = ProjectProtocolSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Admins veem todos os protocolos, clientes veem apenas os seus."""
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
        """Retorna os protocolos vinculados ao projeto da URL."""
        user = self.request.user
        project_pk = self.kwargs.get('project_pk')
        queryset = ProjectProtocol.objects.filter(project_id=project_pk)
        
        if not (user.is_superuser or getattr(user, 'is_admin', False) or getattr(user, 'is_tecnico', False)):
            queryset = queryset.filter(project__created_by=user)
            
        return queryset.order_by('-id')

    def list(self, request, *args, **kwargs):
        """
        [GET] /api/v1/projects/<project_pk>/protocols/
        Retorna os protocolos envelopados com o status atual e o próximo do projeto.
        """
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(ClientProject, pk=project_pk)
        
        # Chama a lógica atualizada com os campos do seu modelo
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
        notify_protocol_updated(protocolo.project, codebase=protocolo.numero_protocolo, data_limite=protocolo.data_limite)

    # -------------------------------------------------------------------------
    # MÉTODO AUXILIAR AJUSTADO PARA O SEU MODELO
    # -------------------------------------------------------------------------
    def _calcular_status_atual_e_proximo(self, project):
        """
        Calcula o status atual e o próximo utilizando uma esteira linear (fila)
        baseada nos valores reais salvos no banco de dados.
        """        
        # Coleta o histórico mais recente do projeto
        ultimo_historico = ProjectStatusHistory.objects.filter(project=project).first()
        
        # 🟢 A FILA/ESTEIRA: Definição exata da sequência cronológica do seu projeto
        esteira_fluxo = [
            AndamentoDoProjeto.ANALISE_DE_DOCUMENTOS.value,  # 'Em análise de documentos'
            AndamentoDoProjeto.EXECUCAO.value,               # 'Projeto em Execução'
            AndamentoDoProjeto.PAGAMENTO_TRT_ART.value,       # 'Pagamento da TRT/ART'
            AndamentoDoProjeto.ANALISE_TECNICA.value,        # 'Projeto em análise técnica'
            AndamentoDoProjeto.APROVADO.value,               # 'Projeto aprovado'
            AndamentoDoProjeto.VISTORIA.value,               # 'Projeto em vistoria'
            AndamentoDoProjeto.CONCLUIDO.value               # 'Projeto finalizado'
        ]
        
        # Caso o projeto seja novo e não tenha nenhuma linha de histórico ainda
        if not ultimo_historico:
            return {
                'atual': esteira_fluxo[0],
                'proximo': esteira_fluxo[1]
            }
        
        # Captura o status bruto gravado no banco (pode ser chave ou valor)
        status_salvo = ultimo_historico.new_status
        
        # Normalização: Garante que vamos trabalhar sempre com o texto descritivo (ex: 'Projeto em análise técnica')
        status_atual_display = AndamentoDoProjeto.get_display_name(status_salvo) or status_salvo
        
        # 🛑 TRATAMENTO DE DESVIO: O status 'REPROVADO' não segue a linha reta da esteira
        if status_salvo in ['REPROVADO', AndamentoDoProjeto.REPROVADO.value]:
            return {
                'atual': AndamentoDoProjeto.REPROVADO.value,
                'proximo': "Aguardando correções / Reenvio de documentos"
            }
            
        try:
            # Descobre a posição (índice) do status atual dentro da nossa fila
            index_atual = esteira_fluxo.index(status_atual_display)
            
            # Se não for o último passo da fila, o próximo será o elemento seguinte
            if index_atual + 1 < len(esteira_fluxo):
                proximo_display = esteira_fluxo[index_atual + 1]
            else:
                proximo_display = "Nenhum (Projeto Finalizado)"
                
        except ValueError:
            # Fallback de segurança caso o texto do banco não exista na nossa esteira por algum motivo
            proximo_display = "Não identificado (Fora do fluxo padrão)"
            
        return {
            'atual': status_atual_display,
            'proximo': proximo_display
        }
        
class ProjectViewSet(viewsets.ModelViewSet):
    queryset = ClientProject.objects.all().order_by('-created_at')
    filter_backends = [DjangoFilterBackend]
    pagination_class = None
    filterset_fields = ['created_by', 'codigoCliente']

    def get_permissions(self):
        return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return ClientProject.objects.none()
        user = self.request.user
        if user.is_superuser or user.is_admin or user.is_tecnico:
            return ClientProject.objects.select_related('created_by').order_by('-created_at')
        return ClientProject.objects.filter(created_by=user).select_related('created_by').order_by('-created_at')

    def get_serializer_class(self):
        if getattr(self, "swagger_fake_view", False):
            return ProjectInfoSerializer
        user = self.request.user
        if self.action in ['update', 'partial_update']:
             return TecnicoClientProjectSerializer
        if user.is_authenticated and (user.is_tecnico or user.is_cliente):
            return TecnicoClientProjectSerializer
        if self.action == 'list':
            return ProjectListSerializer
        return ProjectInfoSerializer
    
    @action(detail=False, methods=['get'])
    def meus_projetos(self, request):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
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
            # NOTIFICAÇÃO: Nova função da Camada 4
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

        # 🟢 Agregação com normalização de unidades para o projeto individual
        total_mod_kw = 0.0
        total_inv_kw = 0.0
        for material in project.material_lists.all():
            qtd = float(material.quantidade or 0)
            pot_bruta = float(material.potencia or 0)
            tipo = str(material.tipo or '').lower()
            unidade = str(material.unidade_de_medida or '').lower().strip()
            
            # 🟢 Filtro de Unidade de Medida
            if 'kw' in unidade:
                pot_kw = pot_bruta
            else:
                pot_kw = pot_bruta / 1000.0
                
            total_linha_kw = qtd * pot_kw
            
            if 'modulo' in tipo or 'módulo' in tipo:
                total_mod_kw += total_linha_kw
            elif 'inversor' in tipo:
                total_inv_kw += total_linha_kw

        # Invoca a regra matemática pura do utils
        dados_calculados = calcular_regras_potencia_e_valor({
            'total_modulos_kw': total_mod_kw,
            'total_inversores_kw': total_inv_kw
        })

        row = [
            project.nomeTitular, 
            project.classe, 
            project.get_status_display(), 
            project.codigoCliente, 
            data_ingresso,
            f"{dados_calculados['potencia_calculada']:.2f}",
            f"{dados_calculados['valor_calculado']:.2f}"
        ]
        ws.append(row)

        # Ajuste automático do tamanho das colunas
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
            # A nova abstração cuida de salvar a notificação, alertar os Admins via WS, e (futuramente) por e-mail.
            notify_inspection_requested(projeto, request.user)
            
            projeto.pedido_vistoria = True
            projeto.save()
            
            return Response({"message": "Vistoria solicitada com sucesso!"}, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response(
                {"error": "Erro ao processar a solicitação de vistoria.", "details": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ProjectDocumentListView(viewsets.ModelViewSet):
    serializer_class = DocumentUploadSerializer
    queryset = ProjectDocument.objects.all().order_by('-created_at')
    pagination_class = None

    def get_queryset(self):
        project_pk = self.kwargs.get('project_pk')
        if getattr(self, "swagger_fake_view", False) or not project_pk:
            return ProjectDocument.objects.none()
        return ProjectDocument.objects.filter(project_id=project_pk).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(ClientProject, pk=project_pk)
        
        documento = serializer.save(project=project)
        tipo_doc = documento.document_type
        user_request = self.request.user
        
        # 1. Regra: Admin adicionando 'boleto'
        if tipo_doc == 'boleto' and (user_request.is_admin or user_request.is_staff or user_request.is_superuser):
            notify_boleto_added(project, documento)
            
        # 2. Regra: Cliente adicionando 'comprovante_de_pagamento'
        elif tipo_doc == 'comprovante_de_pagamento' and user_request == project.created_by:
            notify_comprovante_added(project, documento, user_request)

    def perform_update(self, serializer):
        novo_status = serializer.validated_data.get('status')
        
        if novo_status == 'APPROVED':
            instance = serializer.save(approved_at=timezone.now())
        else:
            instance = serializer.save()

        user_request = self.request.user
        
        # 1. GATILHOS DE MUDANÇA DE STATUS
        if novo_status == ProjectDocument.STATUS_REJECTED:
            notify_document_rejected(instance.project, instance)
            
        elif novo_status == ProjectDocument.STATUS_APPROVED:
            notify_document_approved(instance.project, instance)

        # 2. GATILHOS DE ALTERAÇÃO DE ARQUIVO FÍSICO
        if 'arquivo' in serializer.validated_data:
            tipo_doc = instance.document_type
            if tipo_doc == 'boleto' and (user_request.is_admin or user_request.is_staff or user_request.is_superuser):
                notify_boleto_added(instance.project, instance)
            elif tipo_doc == 'comprovante_de_pagamento' and user_request == instance.project.created_by:
                notify_comprovante_added(instance.project, instance, user_request)

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
        
        if not (request.user.is_superuser or request.user.is_admin or request.user.is_tecnico or request.user == project.created_by):
            raise PermissionDenied("Sem permissão para download.")

        if not document.arquivo:
            return Response({"error": "O documento não possui um arquivo anexado."}, status=status.HTTP_404_NOT_FOUND)

        file_path = document.arquivo.path

        if not os.path.exists(file_path):
            return Response({"error": "Arquivo físico não encontrado."}, status=status.HTTP_404_NOT_FOUND)

        response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        return response
    
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