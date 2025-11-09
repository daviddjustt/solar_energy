from rest_framework import serializers
from .models import ClientProject, ConsumerUnit, ProjectDocument
from .utils import VOLTAGEM_LABELS, VOLTAGEM_MAP


# Serializer para Unidades Consumidoras
class ConsumerUnitSerializer(serializers.ModelSerializer):
    # codigoCliente = serializers.CharField(source='codigoCliente')
    # project = serializers.PrimaryKeyRelatedField(queryset=ClientProject.objects.all(), read_only=True)
    class Meta:
        model = ConsumerUnit
        fields = "__all__"
        read_only_fields = ['project']

# Serializer para Upload de Documentos
class DocumentUploadSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProjectDocument
        fields = "__all__"
        read_only_fields = [
            'is_approved', 'project',
        ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            
            # Controle de permissões por tipo de documento
            if hasattr(self, 'initial_data') and self.initial_data:
                document_type = self.initial_data.get('document_type')
                
                # Cliente não pode criar/editar boleto
                if user.is_cliente and document_type == 'boleto':
                    raise serializers.ValidationError({
                        'document_type': 'Clientes não podem criar ou editar boletos.'
                    })

    def validate(self, data):
        request = self.context.get('request')
        user = request.user if request else None
        document_type = data.get('document_type')
        
        # Validações de permissão
        if user and user.is_cliente and document_type == 'boleto':
            raise serializers.ValidationError({
                'document_type': 'Clientes não podem criar ou editar boletos.'
            })
        
        # Admin e técnico podem criar boleto
        if document_type == 'boleto' and not (user.is_admin or user.is_tecnico or user.is_superuser):
            raise serializers.ValidationError({
                'document_type': 'Apenas administradores e técnicos podem criar boletos.'
            })
        
        return data

# Serializer para as informações básicas do Projeto
class ProjectInfoSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    valor_total = serializers.ReadOnlyField()
    resumo_financeiro = serializers.ReadOnlyField()

    # Campos para documentos de pagamento
    boleto = serializers.SerializerMethodField()
    comprovante_pagamento = serializers.SerializerMethodField()
    voltagem_label = serializers.SerializerMethodField()
    
    class Meta:
        model = ClientProject
        fields = "__all__" # 'codigoCliente' será incluído aqui automaticamente do request body
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'valor_total', 'resumo_financeiro')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        read_only_fields = ['created_by', 'created_at', 'updated_at']
        for field_name in read_only_fields:
            if field_name in self.fields:
                self.fields[field_name].read_only = True

    def validate_voltagem(self, value):
        """
        Valida e converte o value em label

        Recebe: "127"
        Retorna: "Monofásico - 127V"
        """
        if not value:
            raise serializers.ValidationError("Voltagem é obrigatória")

        value_str = str(value).strip()

        # Se já é um label completo (vindo do banco), retornar como está
        if value_str in [choice[0] for choice in ClientProject.VOLTAGEM_CHOICES]:
            return value_str

        # Se é um value (vindo do frontend), converter em label
        if value_str in VOLTAGEM_MAP:
            converted_value = VOLTAGEM_MAP[value_str]
            return converted_value

        # Se não encontrou, retornar erro
        valid_values = ', '.join(VOLTAGEM_MAP.keys())
        raise serializers.ValidationError(
            f"Voltagem inválida. Valores aceitos: {valid_values}"
        )
    
    def get_boleto(self, obj):
        """Retorna informações do boleto"""
        boleto = obj.documents.filter(document_type='boleto').first()
        if boleto:
            return {
                'id': boleto.id,
                'file_url': boleto.arquivo.url if boleto.arquivo else None,
                'status': boleto.status,
                'created_at': boleto.created_at,
                'can_edit': self._can_edit_boleto()
            }
        return None

    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem
    
    def get_comprovante_pagamento(self, obj):
        """Retorna informações do comprovante"""
        comprovante = obj.documents.filter(document_type='comprovante_de_pagamento').first()
        if comprovante:
            return {
                'id': comprovante.id,
                'file_url': comprovante.arquivo.url if comprovante.arquivo else None,
                'status': comprovante.status,
                'can_edit': self._can_edit_comprovante(obj)
            }
        return None

    def _can_edit_boleto(self):
        """Verifica se o usuário pode editar boleto"""
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return False
        user = request.user
        return user.is_admin or user.is_tecnico or user.is_superuser

    def _can_edit_comprovante(self, project):
        """Verifica se o usuário pode editar comprovante"""
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return False
        user = request.user
        # Cliente pode editar se for o dono do projeto, admin/técnico sempre podem
        return (user.is_cliente and project.created_by == user) or user.is_admin or user.is_tecnico or user.is_superuser

    def validate_money(self, data):
        """Validação customizada no serializer"""
        tipo_financeiro = data.get('tipo_financeiro')
        parcelas = data.get('parcelas')
        valor_financeiro = data.get('valor_financeiro')

        # Validar parcelas para mensalidade
        if tipo_financeiro == 'mensalidade':
            if not parcelas or parcelas <= 0:
                raise serializers.ValidationError({
                    'parcelas': 'Número de parcelas é obrigatório e deve ser maior que zero para mensalidade.'
                })
        else:
            # Se não for mensalidade, remove parcelas
            data['parcelas'] = None

        return data
    

    def to_representation_money(self, instance):
        """Customiza a representação para incluir informações financeiras"""
        data = super().to_representation_money(instance)
        
        # Informações do usuário criador
        if instance.created_by:
            data['created_by_info'] = {
                'uuid': str(instance.created_by.uuid),
                'name': instance.created_by.name,
                'email': instance.created_by.email
            }
        
        # Informações financeiras formatadas
        data['financeiro_info'] = {
            'tipo': instance.get_tipo_financeiro_display(),
            'valor_formatado': f"R$ {instance.valor_financeiro:,.2f}",
            'parcelas': instance.parcelas if instance.tipo_financeiro == 'mensalidade' else None,
            'valor_total_formatado': f"R$ {instance.valor_total:,.2f}",
            'resumo': instance.resumo_financeiro
        }
        
        return data

    def to_representation_user(self, instance):
        """Customiza a representação para incluir informações do usuário"""
        data = super().to_representation_user(instance)
        if instance.created_by:
            data['created_by_info'] = {
                'uuid': str(instance.created_by.uuid),
                'name': instance.created_by.name,
                'email': instance.created_by.email
            }
        return data

    def validate_tipoDocumento(self, value):
        if value :
            return value

    def validate_documents(self, data):
        tipo_documento = data.get('tipoDocumento', '').lower()
        documento = data.get('client_document')

        if tipo_documento == 'cpf':
            data['tipoDocumento'] = 'PF'
            if documento:
                import re
                if not re.match(r'^\d{3}\.\d{3}\.\d{3}-\d{2}$', documento):
                    raise serializers.ValidationError({
                        'client_document': 'CPF deve estar no formato XXX.XXX.XXX-XX'
                    })
        elif tipo_documento == 'PJ':
            data['tipoDocumento'] = 'PJ'
            if documento:
                import re
                if not re.match(r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$', documento):
                    raise serializers.ValidationError({
                        'client_document': 'CNPJ deve estar no formato XX.XXX.XXX/XXXX-XX'
                    })
        else:
            if documento:
                raise serializers.ValidationError({'tipoDocumento': 'Tipo de documento é obrigatório quando o documento é fornecido.'})

        # Validação de coordenadas atualizada conforme seu código
        lat_fields = [data.get('lat_degrees'), data.get('lat_minutes'), data.get('lat_seconds')]
        long_fields = [data.get('long_degrees'), data.get('long_minutes'), data.get('long_seconds')]

        if any(f is not None for f in lat_fields) and not all(f is not None for f in lat_fields):
            raise serializers.ValidationError({
                'coordinates': 'Todos os campos de latitude (graus, minutos, segundos) devem ser fornecidos se algum for.'
            })
        if any(f is not None for f in long_fields) and not all(f is not None for f in long_fields):
            raise serializers.ValidationError({
                'coordinates': 'Todos os campos de longitude (graus, minutos, segundos) devem ser fornecidos se algum for.'
            })
        return data

    def create(self, validated_data):
        validated_data.pop('tipoDocumento', None)
        project = ClientProject.objects.create(**validated_data)
        return project

    def update(self, instance, validated_data):
        validated_data.pop('tipoDocumento', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem
    

# Serializer para Listagem de Projetos
class ProjectListSerializer(serializers.ModelSerializer):
    codigoCliente = serializers.CharField(read_only=True)
    nomeTitular = serializers.CharField( read_only=True)
    classe = serializers.CharField( read_only=True)
    celular = serializers.CharField( read_only=True)
    tipoDocumento = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()
    consumer_units_count = serializers.SerializerMethodField()

    class Meta:
        model = ClientProject
        fields = "__all__"
    
    def validate_voltagem(self, value):
        """
        Valida e converte o value em label

        Recebe: "127"
        Retorna: "Monofásico - 127V"
        """
        if not value:
            raise serializers.ValidationError("Voltagem é obrigatória")

        value_str = str(value).strip()

        # Se já é um label completo (vindo do banco), retornar como está
        if value_str in [choice[0] for choice in ClientProject.VOLTAGEM_CHOICES]:
            return value_str

        # Se é um value (vindo do frontend), converter em label
        if value_str in VOLTAGEM_MAP:
            converted_value = VOLTAGEM_MAP[value_str]
            return converted_value

        # Se não encontrou, retornar erro
        valid_values = ', '.join(VOLTAGEM_MAP.keys())
        raise serializers.ValidationError(
            f"Voltagem inválida. Valores aceitos: {valid_values}"
        )

    def get_tipoDocumento(self, obj):
        return 'cpf' if obj.tipoDocumento == 'PF' else 'PJ'

    def get_documents_count(self, obj):
        return obj.documents.count()

    def get_consumer_units_count(self, obj):
        return obj.consumer_units.count()

     
    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem
    

class TecnicoClientProjectSerializer(serializers.ModelSerializer):
    """Serializer para técnicos e clientes - campos financeiros são read-only"""
    
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    valor_total = serializers.ReadOnlyField()
    resumo_financeiro = serializers.ReadOnlyField()
    
    # Campos para documentos de pagamento
    boleto = serializers.SerializerMethodField()
    comprovante_pagamento = serializers.SerializerMethodField()
    
    # Campos financeiros como read-only para técnicos e clientes
    tipo_financeiro = serializers.CharField(read_only=True)
    valor_financeiro = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    parcelas = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = ClientProject
        fields = '__all__'
        read_only_fields = (
            'created_by', 'created_at', 'updated_at', 
            'valor_total', 'resumo_financeiro',
            'tipo_financeiro', 'valor_financeiro', 'parcelas'  # Campos financeiros
        )
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        read_only_fields = ['created_by', 'created_at', 'updated_at']
        for field_name in read_only_fields:
            if field_name in self.fields:
                self.fields[field_name].read_only = True
    
    def get_boleto(self, obj):
        """Retorna informações do boleto"""
        boleto = obj.documents.filter(document_type='boleto').first()
        if boleto:
            return {
                'id': boleto.id,
                'file_url': boleto.arquivo.url if boleto.arquivo else None,
                'status': boleto.status,
                'can_edit': self._can_edit_boleto()
            }
        return None

    def get_comprovante_pagamento(self, obj):
        """Retorna informações do comprovante"""
        comprovante = obj.documents.filter(document_type='comprovante_de_pagamento').first()
        if comprovante:
            return {
                'id': comprovante.id,
                'file_url': comprovante.arquivo.url if comprovante.arquivo else None,
                'status': comprovante.status,
                'can_edit': self._can_edit_comprovante(obj)
            }
        return None

    def _can_edit_boleto(self):
        """Técnicos podem editar boleto, clientes não"""
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return False
        user = request.user
        return user.is_tecnico

    def _can_edit_comprovante(self, project):
        """Clientes podem editar comprovante se for seu projeto, técnicos sempre podem"""
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return False
        user = request.user
        return (user.is_cliente and project.created_by == user) or user.is_tecnico
    
    def validate(self, data):
        """Validação para impedir modificação de campos financeiros por técnicos/clientes"""
        user = self.context['request'].user
        
        # Verificar se é um técnico ou cliente tentando modificar campos financeiros
        if user.groups.filter(name__in=['Tecnicos', 'Clientes']).exists():
            financial_fields = ['tipo_financeiro', 'valor_financeiro', 'parcelas']
            
            for field in financial_fields:
                if field in data:
                    raise serializers.ValidationError({
                        field: 'Usuários do tipo Técnico ou Cliente não podem modificar campos financeiros.'
                    })
        
        return data
    
    def validate_voltagem(self, value):
        """
        Valida e converte o value em label

        Recebe: "127"
        Retorna: "Monofásico - 127V"
        """
        if not value:
            raise serializers.ValidationError("Voltagem é obrigatória")

        value_str = str(value).strip()

        # Se já é um label completo (vindo do banco), retornar como está
        if value_str in [choice[0] for choice in ClientProject.VOLTAGEM_CHOICES]:
            return value_str

        # Se é um value (vindo do frontend), converter em label
        if value_str in VOLTAGEM_MAP:
            converted_value = VOLTAGEM_MAP[value_str]
            return converted_value

        # Se não encontrou, retornar erro
        valid_values = ', '.join(VOLTAGEM_MAP.keys())
        raise serializers.ValidationError(
            f"Voltagem inválida. Valores aceitos: {valid_values}"
        )
    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem
    
# Serializer específico para documentos de pagamento
class PaymentDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDocument
        fields = ['id', 'document_type', 'status']
        read_only_fields = ['status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            
            # Se for cliente, só pode criar/editar comprovante
            if user.is_cliente:
                if self.instance and self.instance.document_type == 'boleto':
                    # Cliente não pode editar boleto
                    for field in self.fields:
                        if field != 'id':
                            self.fields[field].read_only = True
