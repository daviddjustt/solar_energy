# solar/documents/admin.py
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone # Importar timezone
from .models import ClientProject, ConsumerUnit, ProjectDocument
from simple_history.admin import SimpleHistoryAdmin # Importar se estiver usando simple_history

# Inline para ConsumerUnit (para ser aninhado em ClientProject)
class ConsumerUnitInline(admin.TabularInline):
    model = ConsumerUnit
    extra = 1 # Quantidade de formulários vazios para adicionar
    fields = ('client_code', 'percentage', 'voltage')
    verbose_name = "Unidade Consumidora"
    verbose_name_plural = "Unidades Consumidoras"

# Inline para ProjectDocument (para ser aninhado em ClientProject)
class ProjectDocumentInline(admin.TabularInline):
    model = ProjectDocument
    extra = 1
    # Campos visíveis no inline
    fields = ('document_type', 'arquivo', 'file_type', 'description', 'status', 'rejection_reason')
    # Campos somente leitura para todos os usuários
    readonly_fields = ('file_type', 'approved_at', 'approved_by')
    verbose_name = "Documento do Projeto"
    verbose_name_plural = "Documentos do Projeto"

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        qs = super().get_queryset(request)
        return qs # Retorna todos os documentos por padrão

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Se o usuário NÃO for superusuário, desabilita a edição de status e campos relacionados
        if not request.user.is_superuser:
            # Desabilita os campos de status para usuários não superusuários
            # Note: Acessar base_fields diretamente pode ser problemático com formsets,
            # mas para fins de demonstração é funcional.
            # Uma abordagem mais robusta seria criar um Form customizado para o inline.
            for field_name in ['status', 'rejection_reason']:
                if field_name in formset.form.base_fields:
                    formset.form.base_fields[field_name].disabled = True
            
            # Garante que approved_at e approved_by sejam sempre readonly para não-superusuários
            # (já estão em readonly_fields, mas reforça a lógica de permissão)
            if 'approved_at' not in self.readonly_fields:
                self.readonly_fields = self.readonly_fields + ('approved_at',)
            if 'approved_by' not in self.readonly_fields:
                self.readonly_fields = self.readonly_fields + ('approved_by',)

        return formset

# Admin para ClientProject
@admin.register(ClientProject)
class ClientProjectAdmin(SimpleHistoryAdmin): # Use SimpleHistoryAdmin se estiver usando simple_history
    list_display = (
        'client_code',
        'project_holder_name',
        'project_class',
        'email',
        'client_type',
        'documento_label', # Propriedade customizada do model
        'documentation_complete',
        'approved_documents_count', # Novo campo para contagem
        'in_analysis_documents_count', # Novo campo para contagem
        'rejected_documents_count', # Novo campo para contagem
        'total_documents_count', # Novo campo para contagem
        'created_at',
        'get_created_by_email', # Renomeado para evitar conflito com o método
    )
    list_filter = ('client_type', 'documentation_complete', 'voltage', 'created_at')
    search_fields = ('client_code', 'project_holder_name', 'email', 'documento', 'cep', 'city')
    # documentation_complete agora é calculado, então deve ser readonly
    readonly_fields = (
        'created_at', 'updated_at', 'documentation_complete',
        'approved_documents_count', 'in_analysis_documents_count',
        'rejected_documents_count', 'total_documents_count'
    )
    fieldsets = (
        ("Informações Básicas do Cliente", {
            'fields': ('client_code', 'project_holder_name', 'project_class', 'email', 'client_type', 'documento'),
        }),
        ("Endereço", {
            'fields': ('cep', 'street', 'number', 'neighborhood', 'city', 'complement'),
        }),
        ("Contato e Localização", {
            'fields': ('phone', 'latitude', 'longitude'),
            'description': "Insira as coordenadas decimais para a localização do projeto."
        }),
        ("Informações Técnicas e Status", {
            'fields': ('voltage', 'documentation_complete', 'approved_documents_count', 'in_analysis_documents_count', 'rejected_documents_count', 'total_documents_count'),
        }),
        ("Metadados", {
            'fields': ('created_at', 'updated_at', 'created_by'), # created_by é definido no save_model
            'classes': ('collapse',), # Colapsa esta seção por padrão
        }),
    )
    inlines = [ConsumerUnitInline, ProjectDocumentInline]

    def get_created_by_email(self, obj):
                if obj.created_by:
                    # Assumindo que seu User model tem um campo 'email'
                    return obj.created_by.email
                return "-"
    get_created_by_email.short_description = "Criado por" # Nome da coluna no admin
    get_created_by_email.admin_order_field = 'created_by__email' # Permite ordenar por email

    def save_model(self, request, obj, form, change):
        if not obj.pk: # Se for um novo objeto
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('created_by') # Otimiza a busca do usuário criador

    # Exibe o nome do usuário criador na lista de display
    def created_by_display(self, obj):
        return obj.created_by.username if obj.created_by else 'N/A'
    created_by_display.short_description = "Criado por"

# Admin para ConsumerUnit (se precisar de uma página de administração separada)
@admin.register(ConsumerUnit)
class ConsumerUnitAdmin(SimpleHistoryAdmin): # Use SimpleHistoryAdmin se estiver usando simple_history
    list_display = ('client_code', 'project', 'percentage', 'voltage')
    list_filter = ('project', 'voltage')
    search_fields = ('client_code', 'project__client_code', 'project__project_holder_name')
    # Adicione raw_id_fields para o ForeignKey 'project' se tiver muitos projetos
    # raw_id_fields = ('project',)

# Admin para ProjectDocument (se precisar de uma página de administração separada)
@admin.register(ProjectDocument)
class ProjectDocumentAdmin(SimpleHistoryAdmin): # Use SimpleHistoryAdmin se estiver usando simple_history
    list_display = (
        'project',
        'document_type',
        'file_type',
        'status', # Mudado de is_approved para status
        'approved_at', # Adicionado
        'approved_by_display', # Adicionado
    )
    list_filter = ('document_type', 'file_type', 'status', 'project') # Mudado de is_approved para status
    search_fields = ('project__client_code', 'description', 'rejection_reason')
    # approved_at e file_type são definidos automaticamente
    readonly_fields = ('file_type', 'approved_at', 'approved_by')
    # raw_id_fields = ('project', 'approved_by') # Use se tiver muitos projetos/usuários
    fieldsets = (
        (None, {
            'fields': ('project', 'document_type', 'arquivo', 'description', 'file_type'),
        }),
        ("Status de Aprovação", {
            'fields': ('status', 'rejection_reason', 'approved_at', 'approved_by'), # Mudado de is_approved para status
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Se o usuário NÃO for superusuário, desabilita a edição de status e razão de rejeição
        if not request.user.is_superuser:
            form.base_fields['status'].disabled = True
            form.base_fields['rejection_reason'].disabled = True
            # Garante que approved_at e approved_by sejam sempre readonly para não-superusuários
            if 'approved_at' not in self.readonly_fields:
                self.readonly_fields = self.readonly_fields + ('approved_at',)
            if 'approved_by' not in self.readonly_fields:
                self.readonly_fields = self.readonly_fields + ('approved_by',)
        return form

    # Sobrescreve o método save_model para definir approved_by e approved_at
    def save_model(self, request, obj, form, change):
        # Lógica para definir approved_by e approved_at baseada no status
        if obj.status == ProjectDocument.APPROVED and not obj.approved_by:
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
        elif obj.status != ProjectDocument.APPROVED and obj.approved_by:
            # Se o status mudou de APROVADO para outro, limpa a data/usuário de aprovação
            obj.approved_by = None
            obj.approved_at = None
        
        # Se o status não for REJECTED, limpa a razão de rejeição
        if obj.status != ProjectDocument.REJECTED:
            obj.rejection_reason = None

        super().save_model(request, obj, form, change)

    # Exibe o nome do usuário aprovador na lista de display
    def approved_by_display(self, obj):
        return obj.approved_by.username if obj.approved_by else 'N/A'
    approved_by_display.short_description = "Aprovado por"

