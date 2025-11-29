from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from .models import ClientProject, ConsumerUnit, ProjectDocument, ListaDeMateriais
from .utils import VOLTAGEM_LABELS, VOLTAGEM_MAP
from solar.files.utils import DOCUMENT_TYPE_CHOICES

class VoltageField(serializers.CharField):
    """
    Campo customizado que converte o 'value' do frontend (ex: "127")
    para o 'label' completo (ex: "Monofásico - 127V") antes da validação do modelo.
    """

    def to_internal_value(self, data):
        """
        Este método é chamado pelo DRF para converter o dado de entrada (frontend)
        para o formato interno (para o modelo).
        """
        if not data:
            raise serializers.ValidationError("Voltagem é obrigatória")

        value_str = str(data).strip()

        # 1. Tenta converter o 'value' curto (ex: "127") para o 'label' completo
        converted_label = VOLTAGEM_MAP.get(value_str)

        if converted_label:
            return converted_label # Retorna o label completo

        # 2. Se não foi um 'value' curto, verifica se já é um 'label' completo (para updates ou dados diretos)
        # Isso é importante para que o campo aceite o valor já salvo no banco
        valid_model_choices = [choice[0] for choice in ClientProject.VOLTAGEM_CHOICES]
        if value_str in valid_model_choices:
            return value_str

        # 3. Se não encontrou, é um valor inválido
        valid_short_values = ', '.join(VOLTAGEM_MAP.keys())
        valid_full_labels = ', '.join(valid_model_choices)
        raise serializers.ValidationError(
            f"Voltagem inválida. Valores aceitos (curtos): {valid_short_values}. "
            f"Valores aceitos (completos): {valid_full_labels}. "
            f"Você enviou: '{value_str}'"
        )

    def to_representation(self, value):
        """
        Este método é chamado pelo DRF para converter o dado interno (modelo)
        para o formato de saída (frontend). Retorna o label completo.
        """
        return str(value)

# Serializer para Unidades Consumidoras
class ConsumerUnitSerializer(serializers.ModelSerializer):
    prioridade_is_porcentagem = serializers.BooleanField()
    
    class Meta:
        model = ConsumerUnit
        fields = "__all__"
        read_only_fields = ['project']
    
    def validate(self, data):
        """
        Valida que se 'prioridade_is_porcentagem' for True,
        'porcentagem' não pode ser nulo, vazio ou branco.
        """
        priority_level = data.get('priority_level')
        prioridade_is_porcentagem = data.get('prioridade_is_porcentagem')
        porcentagem = data.get('porcentagem')

        # Se prioridade_is_porcentagem for True, então porcentagem é obrigatório
        if prioridade_is_porcentagem is True:
            if priority_level is None or priority_level == '':
                raise serializers.ValidationError({
                    'priority_level': 'O campo "priority_level" não pode ser vazio, nulo ou branco quando "prioridade_is_porcentagem" é True.'
                })
            if porcentagem is not None and porcentagem != '':
                raise serializers.ValidationError({
                    'porcentagem': 'O campo "porcentagem" deve ser nulo ou vazio quando "prioridade_is_porcentagem" é True.'
                })
            
        elif prioridade_is_porcentagem is False:
            if porcentagem is None or porcentagem == '':
                raise serializers.ValidationError({
                    'porcentagem': 'O campo "porcentagem" não pode ser vazio, nulo ou branco quando "prioridade_is_porcentagem" é False.'
                })
            if priority_level is not None and priority_level != '':
                raise serializers.ValidationError({
                    'priority_level': 'O campo "priority_level" deve ser nulo ou vazio quando "prioridade_is_porcentagem" é False.'
                })
        return data

    
class ListaDeMateriaisSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaDeMateriais
        fields = "__all__"
        read_only_fields = ['project']

class DocumentUploadSerializer(serializers.ModelSerializer):
    """
    Serializer para upload de documentos em projetos.
    O campo 'project' vem da URL (project_pk) e não do body.
    """
    project = serializers.PrimaryKeyRelatedField(
        read_only=True, # ✅ Isso foi adicionado na minha última sugestão
        help_text="ID do projeto ao qual o documento pertence (apenas leitura)."
    )

    class Meta:
        model = ProjectDocument
        fields = "__all__"
        read_only_fields = [
            'created_at',
            'updated_at',
            'approved_at',
            # ✅ Adicione 'project' aqui também para clareza, embora read_only=True já o faça
            # 'project', 
        ]

    def create(self, validated_data):
        # ✅ Pega o project do contexto, pois não virá do validated_data (read_only)
        project = self.context.get('project') 
        if not project:
            raise serializers.ValidationError(
                {'non_field_errors': 'Não foi possível determinar o projeto associado.'}
            )

        # Remove 'project' de validated_data se por algum motivo ele ainda estiver lá
        validated_data.pop('project', None) 

        document = ProjectDocument.objects.create(project=project, **validated_data)
        return document

    def update(self, instance, validated_data):
        # O project já está na instância, não precisa ser atualizado via validated_data
        validated_data.pop('project', None) 
        return super().update(instance, validated_data)

    def validate_document_type(self, value):
        """Validação básica do tipo de documento."""
        valid_types = [choice[0] for choice in DOCUMENT_TYPE_CHOICES]
        if value not in valid_types:
            raise serializers.ValidationError(
                f"Tipo de documento inválido. Escolha entre: {', '.join(valid_types)}"
            )
        return value

    def validate(self, data):
        """
        ✅ VALIDAÇÃO CONSOLIDADA - SEMPRE executada antes de salvar.
        """
        request = self.context.get('request')
        user = request.user if request else None

        if not user:
            raise serializers.ValidationError("Usuário não autenticado.")

        # ===== DETERMINA O PROJETO =====
        # ✅ Pega o project do contexto, pois não virá do validated_data (read_only)
        project = self.context.get('project')
        if not project and self.instance:
            project = self.instance.project

        if not project:
            raise serializers.ValidationError(
                "Não foi possível determinar o projeto associado."
            )

        # ===== DETERMINA O DOCUMENT_TYPE =====
        document_type = data.get('document_type')
        if not document_type and self.instance:
            document_type = self.instance.document_type

        if not document_type:
            raise serializers.ValidationError({
                'document_type': 'Este campo é obrigatório.'
            })

        # ===== VALIDAÇÃO 1: PERMISSÕES PARA BOLETOS (REMOVIDAS TEMPORARIAMENTE) =====
        # if document_type == 'boleto':
        #     if user.is_cliente:
        #         raise serializers.ValidationError({'document_type': 'Clientes não têm permissão para criar ou editar boletos.'})
        #     if not (user.is_admin or user.is_tecnico or user.is_superuser):
        #         raise serializers.ValidationError({'document_type': 'Apenas administradores e técnicos podem criar boletos.'})

        # ===== VALIDAÇÃO 2: COMPROVANTES EXIGEM BOLETO RELACIONADO =====
        if document_type == 'comprovante_de_pagamento':
            # ✅ Pega o valor do campo (pode ser instância, ID ou None)
            related_payment_document = data.get('related_payment_document')

            if not related_payment_document:
                boletos_disponiveis = ProjectDocument.objects.filter(
                    project=project,
                    document_type='boleto'
                ).values_list('id', flat=True)

                if not boletos_disponiveis:
                    raise serializers.ValidationError({
                        'related_payment_document': 'Não é possível enviar comprovante sem um boleto criado primeiro. '
                                                    'Solicite ao administrador que crie um boleto no projeto antes de enviar o comprovante.'
                    })
                else:
                    boletos_ids = ', '.join(map(str, boletos_disponiveis))
                    raise serializers.ValidationError({
                        'related_payment_document': [
                            '🚨 Este campo é OBRIGATÓRIO para comprovantes de pagamento.',
                            f'📌 Para listar: GET /api/v1/projects/{project.id}/payment-documents/',
                            '💡 Exemplo de uso: related_payment_document=51'
                        ]
                    })

            # ✅ VALIDAÇÃO EXTRA: Se forneceu boleto, verifica se é válido
            if related_payment_document:
                # related_payment_document já é uma instância de ProjectDocument aqui (PrimaryKeyRelatedField)
                boleto = related_payment_document 

                if boleto.document_type != 'boleto':
                    raise serializers.ValidationError({
                        'related_payment_document': f"O documento #{boleto.id} não é um boleto válido."
                    })

                # Verifica se pertence ao mesmo projeto
                if boleto.project_id != project.id:
                    raise serializers.ValidationError({
                        'related_payment_document': f'❌ O boleto #{boleto.id} pertence ao projeto #{boleto.project_id}, '
                                                    f'mas você está enviando para o projeto #{project.id}.'
                    })

                # Evita auto-relacionamento
                if self.instance and boleto.id == self.instance.id:
                    raise serializers.ValidationError({
                        'related_payment_document': '❌ Um documento não pode ser relacionado a si mesmo.'
                    })

        return data
# Serializer para as informações básicas do Projeto
class ProjectInfoSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    voltagem = VoltageField()
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

    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem
    
    
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
    voltagem = VoltageField()

    class Meta:
        model = ClientProject
        fields = "__all__"
    

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
    voltagem = VoltageField()
    
    class Meta:
        model = ClientProject
        fields = '__all__'
        read_only_fields = (
            'created_by', 'created_at', 'updated_at', 
        )
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        read_only_fields = ['created_by', 'created_at', 'updated_at']
        for field_name in read_only_fields:
            if field_name in self.fields:
                self.fields[field_name].read_only = True
    
    
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
    
    def get_voltagem_label(self, obj):
        """Retorna o label formatado para exibição"""
        return obj.voltagem
    
# Serializer específico para documentos de pagamento
class PaymentDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDocument
        fields = '__all__'
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

