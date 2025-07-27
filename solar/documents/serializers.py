from rest_framework import serializers
from .models import ClientProject, ConsumerUnit, ProjectDocument
import base64
from django.core.files.base import ContentFile


class ConsumerUnitSerializer(serializers.ModelSerializer):
    # Mapeamento dos campos do request para o model
    codigoCliente = serializers.CharField(source='client_code')
    porcentagem = serializers.DecimalField(source='percentage', max_digits=5, decimal_places=2, required=False)
    tensao = serializers.CharField(source='voltage', required=False)
    
    class Meta:
        model = ConsumerUnit
        fields = ['id', 'codigoCliente', 'porcentagem', 'tensao']
    
    def to_representation(self, instance):
        """Customiza a saída para manter o formato camelCase"""
        data = super().to_representation(instance)
        return data


class DocumentUploadSerializer(serializers.ModelSerializer):
    file_base64 = serializers.CharField(write_only=True, required=False)
    file_name = serializers.CharField(write_only=True, required=False)
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)
    file_url = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    
    class Meta:
        model = ProjectDocument
        fields = [
            'id', 'document_type', 'document_type_display', 'file', 'file_base64', 
            'file_name', 'file_type', 'file_type_display', 'file_url', 'file_size', 
            'description', 'is_approved', 'rejection_reason', 'uploaded_at'
        ]
        read_only_fields = ['file', 'file_type', 'uploaded_at', 'is_approved', 'rejection_reason']

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None

    def get_file_size(self, obj):
        if obj.file:
            return obj.file.size
        return None


class CompleteProjectSerializer(serializers.ModelSerializer):
    # Mapeamento dos campos do request para o model
    codigoCliente = serializers.CharField(source='client_code')
    nomeTitular = serializers.CharField(source='project_holder_name')
    classe = serializers.CharField(source='project_class')
    celular = serializers.CharField(source='phone')
    tipoDocumento = serializers.CharField(write_only=True, required=False)
    
    # Campos de endereço
    logradouro = serializers.CharField(source='street')
    numero = serializers.CharField(source='number')
    bairro = serializers.CharField(source='neighborhood')
    cidade = serializers.CharField(source='city')
    complemento = serializers.CharField(source='complement', required=False, allow_blank=True)
    
    # Campos de coordenadas separadas
    latGraus = serializers.IntegerField(source='lat_degrees', required=False)
    latMin = serializers.IntegerField(source='lat_minutes', required=False)
    latSeg = serializers.IntegerField(source='lat_seconds', required=False)
    longGraus = serializers.IntegerField(source='long_degrees', required=False)
    longMin = serializers.IntegerField(source='long_minutes', required=False)
    longSeg = serializers.IntegerField(source='long_seconds', required=False)
    
    # Campos de relacionamento
    unidades = ConsumerUnitSerializer(source='consumer_units', many=True, required=False)
    documents = DocumentUploadSerializer(many=True, required=False)
    
    # Campos de metadados
    created_by = serializers.StringRelatedField(read_only=True)
    required_documents = serializers.SerializerMethodField()
    documentation_status = serializers.SerializerMethodField()
    
    # Campos adicionais para exibição
    documento_tipo = serializers.CharField(read_only=True)
    documento_label = serializers.CharField(read_only=True)
    
    class Meta:
        model = ClientProject
        fields = [
            'id', 'codigoCliente', 'nomeTitular', 'classe', 'email', 'client_type',
            'cep', 'logradouro', 'numero', 'bairro', 'cidade', 'complemento',
            'documento', 'tipoDocumento', 'documento_tipo', 'documento_label',
            'celular', 'latitude', 'longitude', 'voltage',
            'latGraus', 'latMin', 'latSeg', 'longGraus', 'longMin', 'longSeg',
            'unidades', 'documents', 'documentation_complete', 'required_documents',
            'documentation_status', 'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'documentation_complete', 
            'documento_tipo', 'documento_label', 'latitude', 'longitude'
        ]

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

    def validate_documento(self, value):
        """Validação do documento"""
        if not value:
            raise serializers.ValidationError("Documento é obrigatório.")
        return value

    def validate_tipoDocumento(self, value):
        """Validação do tipo de documento"""
        if value and value.lower() not in ['cpf', 'cnpj']:
            raise serializers.ValidationError("Tipo de documento deve ser 'cpf' ou 'cnpj'.")
        return value

    def validate(self, data):
        """Validação cruzada entre campos"""
        # Determina o client_type baseado no tipoDocumento
        tipo_documento = data.get('tipoDocumento', '').lower()
        documento = data.get('documento')
        
        if tipo_documento == 'cpf':
            data['client_type'] = 'PF'
            if documento:
                import re
                if not re.match(r'^\d{3}\.\d{3}\.\d{3}-\d{2}$', documento):
                    raise serializers.ValidationError({
                        'documento': 'CPF deve estar no formato XXX.XXX.XXX-XX'
                    })
        elif tipo_documento == 'cnpj':
            data['client_type'] = 'PJ'
            if documento:
                import re
                if not re.match(r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$', documento):
                    raise serializers.ValidationError({
                        'documento': 'CNPJ deve estar no formato XX.XXX.XXX/XXXX-XX'
                    })
        
        # Valida coordenadas
        lat_graus = data.get('lat_degrees')
        lat_min = data.get('lat_minutes')
        lat_seg = data.get('lat_seconds')
        long_graus = data.get('long_degrees')
        long_min = data.get('long_minutes')
        long_seg = data.get('long_seconds')
        
        if any([lat_graus, lat_min, lat_seg]) and not all([lat_graus is not None, lat_min is not None, lat_seg is not None]):
            raise serializers.ValidationError({
                'coordinates': 'Todos os campos de latitude (graus, minutos, segundos) devem ser fornecidos.'
            })
        
        if any([long_graus, long_min, long_seg]) and not all([long_graus is not None, long_min is not None, long_seg is not None]):
            raise serializers.ValidationError({
                'coordinates': 'Todos os campos de longitude (graus, minutos, segundos) devem ser fornecidos.'
            })
        
        return data

    def create(self, validated_data):
        # Remove campos que não pertencem ao model
        validated_data.pop('tipoDocumento', None)
        
        # Extrai dados relacionados
        consumer_units_data = validated_data.pop('consumer_units', [])
        documents_data = validated_data.pop('documents', [])
        
        # Define o usuário criador
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
        # Remove campos que não pertencem ao model
        validated_data.pop('tipoDocumento', None)
        
        # Extrai dados relacionados
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
            self._process_documents(instance, documents_data)
        
        return instance

    def _create_documents(self, project, documents_data):
        """Processa e cria documentos a partir dos dados fornecidos"""
        for doc_data in documents_data:
            document_type = doc_data.get('document_type')
            file_data = doc_data.get('file', {})
            
            # Se o arquivo está vazio, apenas cria o registro sem arquivo
            if not file_data or file_data == {}:
                # Verifica se já existe um documento deste tipo
                existing_doc = project.documents.filter(document_type=document_type).first()
                if not existing_doc:
                    ProjectDocument.objects.create(
                        project=project,
                        document_type=document_type,
                        description=doc_data.get('description', ''),
                        file=None
                    )
                continue
            
            # Processa arquivo base64 se fornecido
            file_base64 = file_data.get('file_base64') or doc_data.get('file_base64')
            file_name = file_data.get('file_name') or doc_data.get('file_name') or f"{document_type}.pdf"
            
            if file_base64:
                try:
                    # Decodifica o arquivo base64
                    if ';base64,' in file_base64:
                        format, imgstr = file_base64.split(';base64,')
                        ext = format.split('/')[-1]
                    else:
                        imgstr = file_base64
                        ext = 'pdf'
                    
                    file_content = ContentFile(base64.b64decode(imgstr), name=file_name)
                    
                    # Verifica se já existe um documento deste tipo
                    existing_doc = project.documents.filter(document_type=document_type).first()
                    
                    if existing_doc:
                        # Substitui o documento existente
                        if existing_doc.file:
                            existing_doc.file.delete()
                        existing_doc.file = file_content
                        existing_doc.description = doc_data.get('description', existing_doc.description)
                        existing_doc.is_approved = False
                        existing_doc.rejection_reason = None
                        existing_doc.save()
                    else:
                        # Cria novo documento
                        ProjectDocument.objects.create(
                            project=project,
                            document_type=document_type,
                            file=file_content,
                            description=doc_data.get('description', '')
                        )
                        
                except Exception as e:
                    raise serializers.ValidationError(f"Erro ao processar arquivo {file_name}: {str(e)}")

    def _process_documents(self, project, documents_data):
        """Processa documentos para update"""
        self._create_documents(project, documents_data)

    def to_representation(self, instance):
        """Customiza a representação de saída"""
        data = super().to_representation(instance)
        
        # Converte unidades para o formato esperado
        if instance.consumer_units.exists():
            unidades_data = []
            for unit in instance.consumer_units.all():
                unidades_data.append({
                    'id': unit.id,
                    'codigoCliente': unit.client_code,
                    'porcentagem': str(unit.percentage) if unit.percentage else None,
                    'tensao': unit.voltage
                })
            data['unidades'] = unidades_data
        
        # Adiciona informações extras sobre documentos
        if instance.documents.exists():
            documents_info = []
            for doc in instance.documents.all():
                doc_info = {
                    'id': doc.id,
                    'document_type': doc.document_type,
                    'document_type_display': doc.get_document_type_display(),
                    'file': {
                        'url': doc.file.url if doc.file else None,
                        'name': doc.file_name or (doc.file.name.split('/')[-1] if doc.file else None),
                        'size': doc.file_size or (doc.file.size if doc.file else None),
                        'type': doc.file_type
                    },
                    'description': doc.description,
                    'is_approved': doc.is_approved,
                    'rejection_reason': doc.rejection_reason,
                    'uploaded_at': doc.uploaded_at
                }
                documents_info.append(doc_info)
            data['documents'] = documents_info
        
        # Adiciona tipo de documento baseado no client_type
        data['tipoDocumento'] = 'cpf' if instance.client_type == 'PF' else 'cnpj'
        
        return data


class ProjectListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listagem de projetos"""
    codigoCliente = serializers.CharField(source='client_code', read_only=True)
    nomeTitular = serializers.CharField(source='project_holder_name', read_only=True)
    classe = serializers.CharField(source='project_class', read_only=True)
    celular = serializers.CharField(source='phone', read_only=True)
    tipoDocumento = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()
    consumer_units_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ClientProject
        fields = [
            'id', 'codigoCliente', 'nomeTitular', 'classe', 'email', 'client_type',
            'tipoDocumento', 'celular', 'documentation_complete', 'documents_count',
            'consumer_units_count', 'created_at', 'updated_at'
        ]
    
    def get_tipoDocumento(self, obj):
        return 'cpf' if obj.client_type == 'PF' else 'cnpj'
    
    def get_documents_count(self, obj):
        return obj.documents.count()
    
    def get_consumer_units_count(self, obj):
        return obj.consumer_units.count()
