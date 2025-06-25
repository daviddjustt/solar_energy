from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import ClientProject, ProjectDocument
from .serializers import CompleteProjectSerializer

class CompleteProjectViewSet(viewsets.ModelViewSet):
    serializer_class = CompleteProjectSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return ClientProject.objects.filter(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        """
        Cria um projeto completo com todas as informações:
        - Dados do cliente
        - Unidades consumidoras
        - Documentos (via base64 ou multipart)
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        
        return Response(
            self.get_serializer(project).data, 
            status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        """
        Atualiza um projeto completo com todas as informações
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()

        return Response(self.get_serializer(project).data)

    @action(detail=False, methods=['get'])
    def form_structure(self, request):
        """Retorna a estrutura completa do formulário para o frontend"""
        structure = {
            "project_info": {
                "title": "Informações do Projeto",
                "fields": {
                    "client_code": {"type": "text", "required": True, "label": "Código do cliente"},
                    "project_holder_name": {"type": "text", "required": True, "label": "Nome do titular"},
                    "project_class": {"type": "text", "required": True, "label": "Classe"},
                    "email": {"type": "email", "required": True, "label": "E-mail"},
                    "client_type": {
                        "type": "select", 
                        "required": True, 
                        "label": "Tipo de cliente",
                        "options": [
                            {"value": "PF", "label": "Pessoa Física"},
                            {"value": "PJ", "label": "Pessoa Jurídica"}
                        ]
                    }
                }
            },
            "address": {
                "title": "Endereço",
                "fields": {
                    "cep": {"type": "text", "required": True, "label": "CEP", "mask": "99999-999"},
                    "street": {"type": "text", "required": True, "label": "Logradouro"},
                    "number": {"type": "text", "required": True, "label": "Número"},
                    "neighborhood": {"type": "text", "required": True, "label": "Bairro"},
                    "city": {"type": "text", "required": True, "label": "Cidade"},
                    "complement": {"type": "text", "required": False, "label": "Complemento"}
                }
            },
            "contact": {
                "title": "Contato e Documentos",
                "fields": {
                    "cpf": {"type": "text", "required": True, "label": "CPF", "mask": "999.999.999-99"},
                    "phone": {"type": "text", "required": True, "label": "Celular", "mask": "(99) 99999-9999"}
                }
            },
            "location": {
                "title": "Localização da Usina",
                "fields": {
                    "latitude": {"type": "number", "required": True, "label": "Latitude", "step": "any"},
                    "longitude": {"type": "number", "required": True, "label": "Longitude", "step": "any"}
                }
            },
            "technical": {
                "title": "Informações Técnicas",
                "fields": {
                    "voltage": {"type": "text", "required": True, "label": "Tensão"}
                }
            },
            "consumer_units": {
                "title": "Unidades Consumidoras",
                "type": "array",
                "fields": {
                    "client_code": {"type": "text", "required": True, "label": "Código do cliente"},
                    "percentage": {"type": "number", "required": False, "label": "Porcentagem (%)", "step": "0.01"}
                }
            },
            "documents": {
                "title": "Documentação",
                "type": "array",
                "required_pf": [
                    {"type": "documento_cliente", "label": "Documento do Cliente"},
                    {"type": "unidade_geradora_fatura", "label": "Unidade Geradora (Fatura)"},
                    {"type": "unidades_consumidoras_fatura", "label": "Unidades Consumidoras (Fatura)"},
                    {"type": "lista_material", "label": "Lista de Material"},
                    {"type": "procuracao_assinada", "label": "Procuração Assinada"}
                ],
                "required_pj": [
                    {"type": "documento_cliente", "label": "Documento do Cliente"},
                    {"type": "unidade_geradora_fatura", "label": "Unidade Geradora (Fatura)"},
                    {"type": "unidades_consumidoras_fatura", "label": "Unidades Consumidoras (Fatura)"},
                    {"type": "lista_material", "label": "Lista de Material"},
                    {"type": "procuracao_assinada", "label": "Procuração Assinada"},
                    {"type": "cartao_cnpj", "label": "Cartão CNPJ"},
                    {"type": "inscricao_estadual_municipal", "label": "Inscrição Estadual ou Municipal"},
                    {"type": "contrato_social", "label": "Contrato Social"}
                ],
                "fields": {
                    "document_type": {"type": "select", "required": True, "label": "Tipo do documento"},
                    "file_base64": {"type": "file", "required": True, "label": "Arquivo", "accept": ".pdf,.jpg,.jpeg,.png"},
                    "file_name": {"type": "text", "required": True, "label": "Nome do arquivo"},
                    "description": {"type": "textarea", "required": False, "label": "Descrição"}
                }
            }
        }
        return Response(structure)

    @action(detail=True, methods=['get'])
    def documentation_status(self, request, pk=None):
        """Retorna o status detalhado da documentação"""
        project = self.get_object()
        required_docs = project.get_required_documents()
        
        status_info = {
            "project_id": project.id,
            "client_type": project.client_type,
            "documentation_complete": project.documentation_complete,
            "required_documents": required_docs,
            "documents_status": {}
        }
        
        for doc_type in required_docs:
            doc = project.documents.filter(document_type=doc_type).first()
            status_info["documents_status"][doc_type] = {
                "uploaded": bool(doc),
                "approved": doc.is_approved if doc else False,
                "rejection_reason": doc.rejection_reason if doc else None,
                "uploaded_at": doc.uploaded_at if doc else None,
                "file_type": doc.file_type if doc else None,
                "file_size": doc.file.size if doc and doc.file else None
            }
        
        return Response(status_info)
