# solar/documents/admin.py
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from .models import ClientProject, ConsumerUnit, ProjectDocument
from simple_history.admin import SimpleHistoryAdmin # Importar se estiver usando simple_history

# Inline para ConsumerUnit (para ser aninhado em ClientProject)
class ConsumerUnitInline(admin.TabularInline):
    model = ConsumerUnit
    extra = 1  # Quantidade de formulários vazios para adicionar
    fields = ('client_code', 'percentage', 'voltage')
    verbose_name = "Unidade Consumidora"
    verbose_name_plural = "Unidades Consumidoras"

# Inline para ProjectDocument (para ser aninhado em ClientProject)
class ProjectDocumentInline(admin.TabularInline):
    model = ProjectDocument
    extra = 1
    fields = ('document_type', 'arquivo', 'file_type', 'description', 'is_approved', 'rejection_reason')
    readonly_fields = ('uploaded_at', 'file_type') # file_type é detectado automaticamente
    verbose_name = "Documento do Projeto"
    verbose_name_plural = "Documentos do Projeto"

    # Sobrescreve o queryset para evitar carregar documentos aprovados ou rejeitados na edição
    # Opcional: pode ser removido se quiser ver todos os documentos
    def get_queryset(self, request: HttpRequest) -> QuerySet:
        qs = super().get_queryset(request)
        return qs # Retorna todos os documentos por padrão

    # Opcional: para lidar com a aprovação/rejeição diretamente no inline
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Se o usuário não for superuser ou não tiver permissão específica,
        # pode-se desabilitar a edição de 'is_approved' e 'rejection_reason'
        # if not request.user.is_superuser:
        #     formset.form.base_fields['is_approved'].disabled = True
        #     formset.form.base_fields['rejection_reason'].disabled = True
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
        'created_at',
        'created_by',
    )
    list_filter = ('client_type', 'documentation_complete', 'voltage', 'created_at')
    search_fields = ('client_code', 'project_holder_name', 'email', 'documento', 'cep', 'city')
    readonly_fields = ('created_at', 'updated_at', 'documentation_complete') # created_by é definido automaticamente

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
            'fields': ('voltage', 'documentation_complete'),
        }),
        ("Metadados", {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',), # Colapsa esta seção por padrão
        }),
    )

    inlines = [ConsumerUnitInline, ProjectDocumentInline]

    # Sobrescreve o método save_model para definir o created_by automaticamente
    def save_model(self, request, obj, form, change):
        if not obj.pk: # Se for um novo objeto
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    # Sobrescreve o queryset para ordenar por created_at e exibir o created_by
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('created_by') # Otimiza a busca do usuário criador

    # Exibe o nome do usuário criador na lista de display
    def created_by(self, obj):
        return obj.created_by.username if obj.created_by else 'N/A'
    created_by.short_description = "Criado por"


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
        'is_approved',
        'uploaded_at',
        'approved_by',
    )
    list_filter = ('document_type', 'file_type', 'is_approved', 'project')
    search_fields = ('project__client_code', 'description', 'rejection_reason')
    readonly_fields = ('uploaded_at', 'approved_at', 'file_type')
    # raw_id_fields = ('project', 'approved_by') # Use se tiver muitos projetos/usuários

    fieldsets = (
        (None, {
            'fields': ('project', 'document_type', 'arquivo', 'description', 'file_type'),
        }),
        ("Status de Aprovação", {
            'fields': ('is_approved', 'rejection_reason', 'approved_at', 'approved_by'),
        }),
        ("Metadados", {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # Sobrescreve o método save_model para definir approved_by e approved_at
    def save_model(self, request, obj, form, change):
        if obj.is_approved and not obj.approved_by: # Se foi aprovado agora e não tinha aprovador
            obj.approved_by = request.user
            obj.approved_at = timezone.now() # Importar timezone do django.utils
        elif not obj.is_approved and obj.approved_by: # Se foi desaprovado
            obj.approved_by = None
            obj.approved_at = None
        super().save_model(request, obj, form, change)

    # Exibe o nome do usuário aprovador na lista de display
    def approved_by(self, obj):
        return obj.approved_by.username if obj.approved_by else 'N/A'
    approved_by.short_description = "Aprovado por"

# Lembre-se de importar timezone se usar no save_model do ProjectDocumentAdmin
from django.utils import timezone
