from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from djangorestframework_camel_case.parser import CamelCaseJSONParser
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from .models import ClientProject, ProjectDocument, ConsumerUnit
from .serializers import CompleteProjectSerializer, ProjectListSerializer, DocumentUploadSerializer


class CompleteProjectViewSet(viewsets.ModelViewSet):
    serializer_class = CompleteProjectSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, CamelCaseJSONParser]

    def get_queryset(self):
        """Retorna apenas projetos do usuário autenticado"""
        queryset = ClientProject.objects.filter(created_by=self.request.user)
        
        # Filtros opcionais
        search = self.request.query_params.get('search', None)
        client_type = self.request.query_params.get('client_type', None)
        documentation_complete = self.request.query_params.get('documentation_complete', None)
        voltage = self.request.query_params.get('voltage', None)
        
        if search:
            queryset = queryset.filter(
                Q(client_code__icontains=search) |
                Q(project_holder_name__icontains=search) |
                Q(email__icontains=search) |
                Q(documento__icontains=search) |
                Q(phone__icontains=search) |
                Q(city__icontains=search)
            )
        
        if client_type:
            queryset = queryset.filter(client_type=client_type)
        
        if documentation_complete is not None:
            queryset = queryset.filter(documentation_complete=documentation_complete.lower() == 'true')
        
        if voltage:
            queryset = queryset.filter(voltage=voltage)
        
        return queryset.select_related('created_by').prefetch_related(
            'consumer_units', 'documents'
        ).order_by('-created_at')
    
    def get_serializer_class(self):
        """Usa serializer simplificado para listagem"""
        if self.action == 'list':
            return ProjectListSerializer
        return CompleteProjectSerializer

    def perform_create(self, serializer):
        """Define o usuário criador automaticamente"""
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        """Cria um projeto completo"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, 
            status=status.HTTP_201_CREATED,
            headers=headers
        )

    def update(self, request, *args, **kwargs):
        """Atualiza um projeto"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Remove um projeto"""
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def document_types_by_client(self, request):
        """Retorna tipos de documentos baseado no tipo de cliente"""
        client_type = request.query_params.get('client_type', 'PF')
        
        if client_type == 'PJ':
            document_types = [
                'documento_cliente',
                'lista_material',
                'procuracao_assinada',
                'contrato_social',
                'inscricao_estadual_municipal',
                'cartao_cnpj',
                'unidade_geradora_fatura',
                'unidades_consumidoras_fatura'
            ]
        else:  # PF
            document_types = [
                'documento_cliente',
                'lista_material',
                'procuracao_assinada',
                'unidade_geradora_fatura',
                'unidades_consumidoras_fatura'
            ]
        
        # Retorna estrutura com objetos vazios para cada tipo
        documents = [
            {
                'document_type': doc_type,
                'document_type_display': dict(ProjectDocument.DOCUMENT_TYPE_CHOICES).get(doc_type, doc_type),
                'file': {},
                'uploaded': False,
                'required': True
            }
            for doc_type in document_types
        ]
        
        return Response({
            'client_type': client_type,
            'documents': documents
        })

    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        """Lista todos os documentos de um projeto"""
        project = self.get_object()
        documents = project.documents.all()
        
        document_data = []
        for doc in documents:
            document_data.append({
                'id': doc.id,
                'document_type': doc.document_type,
                'document_type_display': doc.get_document_type_display(),
                'file': {
                    'url': doc.file.url if doc.file else None,
                    'name': doc.file_name or (doc.file.name.split('/')[-1] if doc.file else None),
                    'size': doc.file_size or (doc.file.size if doc.file else 0),
                    'type': doc.file_type
                },
                'description': doc.description,
                'is_approved': doc.is_approved,
                'rejection_reason': doc.rejection_reason,
                'uploaded_at': doc.uploaded_at
            })
        
        return Response({
            'project_id': project.id,
            'client_code': project.client_code,
            'documents': document_data,
            'required_documents': project.get_required_documents(),
            'documentation_complete': project.documentation_complete
        })

    @action(detail=True, methods=['post'])
    def upload_document(self, request, pk=None):
        """Upload de documento para um projeto específico"""
        project = self.get_object()
        document_type = request.data.get('document_type')
        file = request.FILES.get('file')
        file_base64 = request.data.get('file_base64')
        
        if not document_type:
            return Response(
                {'error': 'document_type é obrigatório'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not file and not file_base64:
            return Response(
                {'error': 'file ou file_base64 é obrigatório'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verifica se já existe documento deste tipo
        existing_doc = ProjectDocument.objects.filter(
            project=project, 
            document_type=document_type
        ).first()
        
        try:
            if existing_doc:
                # Atualiza documento existente
                if file:
                    existing_doc.file = file
                elif file_base64:
                    # Processa arquivo base64
                    import base64
                    from django.core.files.base import ContentFile
                    
                    file_name = request.data.get('file_name', f'{document_type}.pdf')
                    if ';base64,' in file_base64:
                        format, imgstr = file_base64.split(';base64,')
                    else:
                        imgstr = file_base64
                    
                    file_content = ContentFile(base64.b64decode(imgstr), name=file_name)
                    existing_doc.file = file_content
                
                existing_doc.description = request.data.get('description', existing_doc.description)
                existing_doc.is_approved = False  # Reset aprovação
                existing_doc.rejection_reason = None
                existing_doc.save()
                doc = existing_doc
            else:
                # Cria novo documento
                doc_data = {
                    'project': project,
                    'document_type': document_type,
                    'description': request.data.get('description', '')
                }
                
                if file:
                    doc_data['file'] = file
                elif file_base64:
                    import base64
                    from django.core.files.base import ContentFile
                    
                    file_name = request.data.get('file_name', f'{document_type}.pdf')
                    if ';base64,' in file_base64:
                        format, imgstr = file_base64.split(';base64,')
                    else:
                        imgstr = file_base64
                    
                    file_content = ContentFile(base64.b64decode(imgstr), name=file_name)
                    doc_data['file'] = file_content
                
                doc = ProjectDocument.objects.create(**doc_data)
            
            return Response({
                'id': doc.id,
                'document_type': doc.document_type,
                'document_type_display': doc.get_document_type_display(),
                'file': {
                    'url': doc.file.url if doc.file else None,
                    'name': doc.file_name or (doc.file.name.split('/')[-1] if doc.file else None),
                    'size': doc.file_size or (doc.file.size if doc.file else 0),
                    'type': doc.file_type
                },
                'description': doc.description,
                'is_approved': doc.is_approved,
                'uploaded_at': doc.uploaded_at
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Erro ao processar arquivo: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['delete'])
    def remove_document(self, request, pk=None):
        """Remove um documento específico"""
        project = self.get_object()
        document_type = request.query_params.get('document_type')
        document_id = request.query_params.get('document_id')
        
        if not document_type and not document_id:
            return Response(
                {'error': 'document_type ou document_id é obrigatório'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            if document_id:
                doc = ProjectDocument.objects.get(id=document_id, project=project)
            else:
                doc = ProjectDocument.objects.get(project=project, document_type=document_type)
            
            doc.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
            
        except ProjectDocument.DoesNotExist:
            return Response(
                {'error': 'Documento não encontrado'}, 
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Estatísticas dos projetos do usuário"""
        queryset = self.get_queryset()
        
        # Estatísticas básicas
        stats = {
            'total_projects': queryset.count(),
            'documentation_complete': queryset.filter(documentation_complete=True).count(),
            'documentation_incomplete': queryset.filter(documentation_complete=False).count(),
            'by_client_type': {
                'PF': queryset.filter(client_type='PF').count(),
                'PJ': queryset.filter(client_type='PJ').count()
            },
            'by_voltage': {},
            'recent_projects': []
        }
        
        # Estatísticas por voltagem
        voltage_stats = queryset.values('voltage').annotate(count=Count('voltage'))
        for item in voltage_stats:
            stats['by_voltage'][item['voltage']] = item['count']
        
        # Projetos recentes
        recent_projects = queryset[:5].values(
            'id', 'client_code', 'project_holder_name', 'created_at', 'documentation_complete'
        )
        stats['recent_projects'] = list(recent_projects)
        
        # Estatísticas de documentos
        total_documents = ProjectDocument.objects.filter(project__created_by=request.user).count()
        approved_documents = ProjectDocument.objects.filter(
            project__created_by=request.user, is_approved=True
        ).count()
        
        stats['documents'] = {
            'total': total_documents,
            'approved': approved_documents,
            'pending': total_documents - approved_documents
        }
        
        return Response(stats)

    @action(detail=True, methods=['post'])
    def validate_documento(self, request, pk=None):
        """Valida o documento (CPF/CNPJ) de um projeto"""
        project = self.get_object()
        
        try:
            is_valid = project.is_documento_valid()
            return Response({
                'project_id': project.id,
                'documento': project.documento,
                'documento_tipo': project.documento_tipo,
                'is_valid': is_valid,
                'message': 'Documento válido' if is_valid else f'{project.documento_tipo} inválido'
            })
        except Exception as e:
            return Response(
                {'error': f'Erro ao validar documento: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def check_documentation(self, request, pk=None):
        """Verifica se a documentação está completa"""
        project = self.get_object()
        
        try:
            is_complete = project.check_documentation_complete()
            required_docs = project.get_required_documents()
            uploaded_docs = list(project.documents.values_list('document_type', flat=True))
            missing_docs = [doc for doc in required_docs if doc not in uploaded_docs]
            
            return Response({
                'project_id': project.id,
                'documentation_complete': is_complete,
                'required_documents': required_docs,
                'uploaded_documents': uploaded_docs,
                'missing_documents': missing_docs,
                'total_required': len(required_docs),
                'total_uploaded': len(uploaded_docs)
            })
        except Exception as e:
            return Response(
                {'error': f'Erro ao verificar documentação: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def convert_coordinates(self, request, pk=None):
        """Converte coordenadas entre formatos decimal e graus/min/seg"""
        project = self.get_object()
        
        try:
            # Se tiver coordenadas em graus/min/seg, converte para decimal
            if all([
                project.lat_degrees is not None,
                project.lat_minutes is not None,
                project.lat_seconds is not None,
                project.long_degrees is not None,
                project.long_minutes is not None,
                project.long_seconds is not None
            ]):
                project.convert_dms_to_coordinates()
            
            # Se tiver coordenadas decimais, converte para graus/min/seg
            elif project.latitude and project.longitude:
                project.convert_coordinates_to_dms()
            
            project.save()
            
            return Response({
                'project_id': project.id,
                'decimal': {
                    'latitude': str(project.latitude) if project.latitude else None,
                    'longitude': str(project.longitude) if project.longitude else None
                },
                'dms': {
                    'latitude': {
                        'degrees': project.lat_degrees,
                        'minutes': project.lat_minutes,
                        'seconds': project.lat_seconds
                    },
                    'longitude': {
                        'degrees': project.long_degrees,
                        'minutes': project.long_minutes,
                        'seconds': project.long_seconds
                    }
                }
            })
        except Exception as e:
            return Response(
                {'error': f'Erro ao converter coordenadas: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['patch'])
    def update_documentation_status(self, request, pk=None):
        """Atualiza manualmente o status da documentação"""
        project = self.get_object()
        documentation_complete = request.data.get('documentation_complete')
        
        if documentation_complete is None:
            return Response(
                {'error': 'documentation_complete é obrigatório'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        project.documentation_complete = documentation_complete
        project.save()
        
        return Response({
            'project_id': project.id,
            'client_code': project.client_code,
            'documentation_complete': project.documentation_complete,
            'updated_at': project.updated_at
        })

    @action(detail=False, methods=['get'])
    def export_projects(self, request):
        """Exporta projetos em formato JSON para backup"""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            'total_projects': queryset.count(),
            'exported_at': timezone.now(),
            'user': request.user.username,
            'projects': serializer.data
        })

    @action(detail=True, methods=['post'])
    def duplicate_project(self, request, pk=None):
        """Duplica um projeto existente"""
        original_project = self.get_object()
        
        try:
            # Cria uma cópia do projeto
            new_project_data = {
                'client_code': f"{original_project.client_code}_COPY",
                'project_holder_name': original_project.project_holder_name,
                'project_class': original_project.project_class,
                'email': original_project.email,
                'client_type': original_project.client_type,
                'cep': original_project.cep,
                'street': original_project.street,
                'number': original_project.number,
                'neighborhood': original_project.neighborhood,
                'city': original_project.city,
                'complement': original_project.complement,
                'documento': original_project.documento,
                'phone': original_project.phone,
                'latitude': original_project.latitude,
                'longitude': original_project.longitude,
                'voltage': original_project.voltage,
                'created_by': request.user
            }
            
            new_project = ClientProject.objects.create(**new_project_data)
            
            # Copia unidades consumidoras
            for unit in original_project.consumer_units.all():
                ConsumerUnit.objects.create(
                    project=new_project,
                    client_code=unit.client_code,
                    percentage=unit.percentage,
                    voltage=unit.voltage
                )
            
            # Nota: Documentos não são copiados por questões de segurança
            
            serializer = self.get_serializer(new_project)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Erro ao duplicar projeto: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
