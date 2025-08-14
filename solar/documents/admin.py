# solar/documents/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import ClientProject, ConsumerUnit, ProjectDocument

# Inline para ConsumerUnit dentro de ClientProject
class ConsumerUnitInline(admin.TabularInline):
    model = ConsumerUnit
    extra = 1 # Quantidade de formulários extras para adicionar
    fields = ('percentage', 'voltage',)
    verbose_name = "Unidade Consumidora"
    verbose_name_plural = "Unidades Consumidoras"

# Inline para ProjectDocument dentro de ClientProject
class ProjectDocumentInline(admin.TabularInline):
    model = ProjectDocument
    extra = 0 # Não exibir formulários extras por padrão, já que documentos são carregados
    fields = ('document_type', 'file_type', 'arquivo', 'status', 'rejection_reason', 'approved_at',)
    readonly_fields = ('approved_at', 'created_at', 'updated_at',)
    verbose_name = "Documento do Projeto"
    verbose_name_plural = "Documentos do Projeto"

@admin.register(ClientProject)
class ClientProjectAdmin(admin.ModelAdmin):
    list_display = (
        'client_code',
        'project_holder_name',
        'email',
        'client_type',
        'documento_label',
        'documentation_complete_display',
        'total_documents_count_display',
        'approved_documents_count_display',
        'in_analysis_documents_count_display',
        'rejected_documents_count_display',
        'created_at',
    )
    list_filter = ('client_type', 'documentation_complete', 'created_at',)
    search_fields = (
        'client_code',
        'project_holder_name',
        'email',
        'documento',
        'cep',
        'city',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'documentation_complete',
        'approved_documents_count',
        'in_analysis_documents_count',
        'rejected_documents_count',
        'total_documents_count',
        'decimal_latitude', # Propriedades calculadas
        'decimal_longitude', # Propriedades calculadas
    )
    fieldsets = (
        (None, {
            'fields': (
                'client_code',
                'project_holder_name',
                'project_class',
                'email',
                'client_type',
                'documento',
                'phone',
            )
        }),
        ('Endereço', {
            'fields': (
                'cep',
                'street',
                'number',
                'neighborhood',
                'city',
                'complement',
            )
        }),
        ('Localização (Graus, Minutos, Segundos)', {
            'fields': (
                ('latGraus', 'latMin', 'latSeg'),
                ('longGraus', 'longMin', 'longSeg'),
                ('decimal_latitude', 'decimal_longitude'), # Exibir valores decimais calculados
            )
        }),
        ('Status da Documentação', {
            'fields': (
                'documentation_complete',
                ('approved_documents_count', 'in_analysis_documents_count', 'rejected_documents_count', 'total_documents_count'),
            )
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at',),
            'classes': ('collapse',), # Colapsa esta seção por padrão
        }),
    )
    inlines = [ConsumerUnitInline, ProjectDocumentInline]

    # Customização para exibir o status da documentação com ícone
    def documentation_complete_display(self, obj):
        if obj.documentation_complete:
            return format_html('<span style="color: green; font-weight: bold;">&#10004; Sim</span>')
        return format_html('<span style="color: red; font-weight: bold;">&#10008; Não</span>')
    documentation_complete_display.short_description = "Doc. Completa"
    documentation_complete_display.admin_order_field = 'documentation_complete'

    # Métodos para exibir contagens de documentos na list_display
    def approved_documents_count_display(self, obj):
        return obj.approved_documents_count
    approved_documents_count_display.short_description = "Docs Aprovados"
    approved_documents_count_display.admin_order_field = 'approved_documents_count'

    def in_analysis_documents_count_display(self, obj):
        return obj.in_analysis_documents_count
    in_analysis_documents_count_display.short_description = "Docs Em Análise"
    in_analysis_documents_count_display.admin_order_field = 'in_analysis_documents_count'

    def rejected_documents_count_display(self, obj):
        return obj.rejected_documents_count
    rejected_documents_count_display.short_description = "Docs Rejeitados"
    rejected_documents_count_display.admin_order_field = 'rejected_documents_count'

    def total_documents_count_display(self, obj):
        return obj.total_documents_count
    total_documents_count_display.short_description = "Total Docs"
    total_documents_count_display.admin_order_field = 'total_documents_count'

    def save_model(self, request, obj, form, change):
        # Garante que as validações do clean() sejam executadas ao salvar no admin
        obj.full_clean()
        super().save_model(request, obj, form, change)

@admin.register(ConsumerUnit)
class ConsumerUnitAdmin(admin.ModelAdmin):
    list_display = ('project','percentage', 'voltage',)
    list_filter = ('project',)
    search_fields = ('project__client_code', 'project__project_holder_name',)
    raw_id_fields = ('project',) # Para projetos com muitos itens, melhora a performance

@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = (
        '__str__', # Usa o método __str__ do modelo
        'project_link', # Link para o projeto relacionado
        'document_type',
        'status',
        'file_type',
        'approved_at',
        'created_at',
    )
    list_filter = ('status', 'document_type', 'file_type', 'project',)
    search_fields = (
        'document_type',
        'project__client_code',
        'project__project_holder_name',
        'rejection_reason',
    )
    raw_id_fields = ('project',) # Usa um widget de pesquisa para ForeignKeys
    readonly_fields = ('created_at', 'updated_at', 'approved_at',)
    fieldsets = (
        (None, {
            'fields': (
                'project',
                'document_type',
                'file_type',
                'arquivo',
            )
        }),
        ('Status e Aprovação', {
            'fields': (
                'status',
                'rejection_reason',
                'approved_at',
            )
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at',),
            'classes': ('collapse',),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

    def project_link(self, obj):
        # Cria um link para a página de edição do ClientProject
        link = reverse("admin:%s_%s_change" % (obj.project._meta.app_label, obj.project._meta.model_name), args=[obj.project.id])
        return format_html('<a href="{}">{}</a>', link, obj.project.client_code)
    project_link.short_description = "Projeto"
    project_link.admin_order_field = 'project__client_code' # Permite ordenar por este campo

