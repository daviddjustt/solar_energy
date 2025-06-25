from rest_framework import serializers
from .models import ClientProject, ConsumerUnit, ProjectDocument
import base64
from django.core.files.base import ContentFile

class ConsumerUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumerUnit
        fields = ['id', 'client_code', 'percentage']

class DocumentUploadSerializer(serializers.ModelSerializer):
    file_base64 = serializers.CharField(write_only=True, required=False)
    file_name = serializers.CharField(write_only=True, required=False)
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)
    file_size = serializers.SerializerMethodField()
    
    class Meta:
        model = ProjectDocument
        fields = [
            'id', 'document_type', 'document_type_display', 'file', 'file_base64', 
            'file_name', 'file_type', 'file_type_display', 'file_size', 'description', 
            'is_approved', 'rejection_reason', 'uploaded_at'
        ]
        read_only_fields = ['file', 'file_type', 'uploaded_at', 'is_approved', 'rejection_reason']

    def get_file_size(self, obj):
        if obj.file:
            return obj.file.size
        return None

class CompleteProjectSerializer(serializers.ModelSerializer):
    consumer_units = ConsumerUnitSerializer(many=True, required=False)
    documents = DocumentUploadSerializer(many=True, required=False)
    created_by = serializers.StringRelatedField(read_only=True)
    required_documents = serializers.SerializerMethodField()
    documentation_status = serializers.SerializerMethodField()
    
    class Meta:
        model = ClientProject
        fields = [
            'id', 'client_code', 'project_holder_name', 'project_class', 'email', 'client_type',
            'cep', 'street', 'number', 'neighborhood', 'city', 'complement',
            'cpf', 'phone', 'latitude', 'longitude', 'voltage',
            'consumer_units', 'documents', 'documentation_complete', 'required_documents',
            'documentation_status', 'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'documentation_complete']

    def get_required_documents(self, obj):
        return obj.get_required_documents()

    def get_documentation_status(self, obj):
        required_docs = obj.get_required_documents()
        uploaded_docs = obj.documents.values_list('document_type', flat=True)
        
        status = {}
        for doc_type in required_docs:
            doc_obj = obj.documents.filter(document_type=doc_type).first()
            status[doc_type] = {
                'uploaded': doc_type in uploaded_docs,
                'approved': doc_obj.is_approved if doc_obj else False,
                'rejection_reason': doc_obj.rejection_reason if doc_obj else None
            }
        
        return status

    def create(self, validated_data):
        consumer_units_data = validated_data.pop('consumer_units', [])
        documents_data = validated_data.pop('documents', [])
        validated_data['created_by'] = self.context['request'].user
        
        # Cria o projeto
        project = ClientProject.objects.create(**validated_data)
        
        # Cria as unidades consumidoras
        for unit_data in consumer_units_data:
            ConsumerUnit.objects.create(project=project, **unit_data)
        
        # Processa e cria os documentos
        self._create_documents(project, documents_data)
        
        return project

    def update(self, instance, validated_data):
        consumer_units_data = validated_data.pop('consumer_units', [])
        documents_data = validated_data.pop('documents', [])
        
        # Atualiza os campos do projeto
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Atualiza unidades consumidoras
        instance.consumer_units.all().delete()
        for unit_data in consumer_units_data:
            ConsumerUnit.objects.create(project=instance, **unit_data)
        
        # Processa documentos se fornecidos
        if documents_data:
            self._create_documents(instance, documents_data)
        
        return instance

    def _create_documents(self, project, documents_data):
        """Processa e cria documentos a partir dos dados fornecidos"""
        for doc_data in documents_data:
            file_base64 = doc_data.pop('file_base64', None)
            file_name = doc_data.pop('file_name', None)
            document_type = doc_data.get('document_type')
            
            if file_base64 and file_name:
                try:
                    # Decodifica o arquivo base64
                    format, imgstr = file_base64.split(';base64,') 
                    ext = format.split('/')[-1]
                    file_data = ContentFile(base64.b64decode(imgstr), name=f"{file_name}")
                    
                    # Verifica se já existe um documento deste tipo
                    existing_doc = project.documents.filter(document_type=document_type).first()
                    
                    if existing_doc:
                        # Substitui o documento existente
                        existing_doc.file.delete()  # Remove arquivo antigo
                        existing_doc.file = file_data
                        existing_doc.description = doc_data.get('description', existing_doc.description)
                        existing_doc.is_approved = False  # Reset aprovação
                        existing_doc.rejection_reason = None
                        existing_doc.save()
                    else:
                        # Cria novo documento
                        ProjectDocument.objects.create(
                            project=project,
                            file=file_data,
                            **doc_data
                        )
                        
                except Exception as e:
                    raise serializers.ValidationError(f"Erro ao processar arquivo {file_name}: {str(e)}")

    def to_representation(self, instance):
        """Customiza a representação de saída"""
        data = super().to_representation(instance)
        
        # Adiciona informações extras sobre documentos
        if instance.documents.exists():
            documents_info = []
            for doc in instance.documents.all():
                doc_info = {
                    'id': doc.id,
                    'document_type': doc.document_type,
                    'document_type_display': doc.get_document_type_display(),
                    'file_type': doc.file_type,
                    'file_type_display': doc.get_file_type_display(),
                    'file_url': doc.file.url if doc.file else None,
                    'file_size': doc.file.size if doc.file else None,
                    'description': doc.description,
                    'is_approved': doc.is_approved,
                    'rejection_reason': doc.rejection_reason,
                    'uploaded_at': doc.uploaded_at
                }
                documents_info.append(doc_info)
            data['documents'] = documents_info
        
        return data
