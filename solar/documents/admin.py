from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count
from django.contrib import messages
from .models import ClientProject, ConsumerUnit, ProjectDocument


class ConsumerUnitInline(admin.TabularInline):
    model = ConsumerUnit
    extra = 1
    fields = ('client_code', 'percentage')  # Atualizado de 'codigoCliente'
    verbose_name = "Unidade Consumidora"
    verbose_name_plural = "Unidades Consumidoras"


class ProjectDocumentInline(admin.StackedInline):
    model = ProjectDocument
    extra = 0
    fields = ('document_type', 'file', 'file_type', 'description', 'is_approved', 'rejection_reason')
    readonly_fields = ('file_type', 'uploaded_at')
    verbose_name = "Documento"
    verbose_name_plural = "Documentos"
    
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and obj.pk:  # Se está editando
            readonly.append('document_type')
        return readonly


@admin.register(ClientProject)
class ClientProjectAdmin(admin.ModelAdmin):
    list_display = (
        'client_code',
        'project_holder_name',
        'client_type',
        'project_class',
        'documento_display',  # Novo campo para mostrar documento formatado
        'documentation_status',
        'consumer_units_count',
        'documents_count',
        'created_at'
    )
    
    list_filter = (
        'client_type',
        'documentation_complete',
        'project_class',
        'created_at',
        'voltage'
    )
    
    search_fields = (
        'client_code',
        'project_holder_name',
        'email',
        'documento',  # Campo unificado para CPF/CNPJ
        'phone'
    )
    
    ordering = ('-created_at',)
    
    readonly_fields = (
        'created_at',
        'updated_at',
        'documentation_complete',
        'created_by',
        'documento_tipo',  # Campo calculado
        'documento_label'  # Campo calculado
    )
    
    inlines = [ConsumerUnitInline, ProjectDocumentInline]
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': (
                'client_code',
                'project_holder_name',
                'project_class',
                'client_type',
                'email'
            )
        }),
        ('Documentos e Contato', {
            'fields': (
                'documento',
                'documento_tipo',  # Campo readonly para mostrar tipo
                'documento_label',  # Campo readonly para mostrar formatado
                'phone'
            )
        }),
        ('Endereço', {
            'fields': (
                'cep',
                'street',
                'number',
                'complement',
                'neighborhood',
                'city'
            )
        }),
        ('Localização da Usina', {
            'fields': (
                'latitude',
                'longitude'
            )
        }),
        ('Informações Técnicas', {
            'fields': (
                'voltage',
            )
        }),
        ('Status e Metadados', {
            'fields': (
                'documentation_complete',
                'created_at',
                'updated_at',
                'created_by'
            ),
            'classes': ('collapse',)
        })
    )
    
    def documento_display(self, obj):
        """Exibe o documento com tipo e formatação"""
        if obj.documento:
            tipo = obj.documento_tipo
            cor = 'blue' if tipo == 'CPF' else 'green'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}: {}</span>',
                cor, tipo, obj.documento
            )
        return '-'
    documento_display.short_description = 'Documento'
    
    def documentation_status(self, obj):
        if obj.documentation_complete:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Completa</span>'
            )
        else:
            return format_html(
                '<span style="color: red; font-weight: bold;">✗ Incompleta</span>'
            )
    documentation_status.short_description = 'Documentação'
    
    def consumer_units_count(self, obj):
        count = obj.consumer_units.count()
        if count > 0:
            return format_html(
                '<span style="color: blue;">{} unidades</span>', count
            )
        return '0 unidades'
    consumer_units_count.short_description = 'Unidades Consumidoras'
    
    def documents_count(self, obj):
        total = obj.documents.count()
        approved = obj.documents.filter(is_approved=True).count()
        if total > 0:
            return format_html(
                '<span style="color: {};">{}/{} docs</span>',
                'green' if approved == total else 'orange',
                approved,
                total
            )
        return '0 docs'
    documents_count.short_description = 'Documentos'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Se está criando um novo objeto
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'consumer_units', 'documents'
        )
    
    actions = ['check_documentation', 'mark_documentation_complete', 'validate_documents']
    
    def check_documentation(self, request, queryset):
        updated = 0
        for project in queryset:
            if project.check_documentation_complete():
                updated += 1
        
        self.message_user(
            request,
            f'{updated} projetos tiveram sua documentação verificada.',
            messages.SUCCESS
        )
    check_documentation.short_description = "Verificar documentação"
    
    def mark_documentation_complete(self, request, queryset):
        updated = queryset.update(documentation_complete=True)
        self.message_user(
            request,
            f'{updated} projetos marcados como documentação completa.',
            messages.SUCCESS
        )
    mark_documentation_complete.short_description = "Marcar documentação como completa"
    
    def validate_documents(self, request, queryset):
        """Nova ação para validar documentos CPF/CNPJ"""
        valid_count = 0
        invalid_count = 0
        
        for project in queryset:
            try:
                project.full_clean()  # Executa todas as validações do modelo
                valid_count += 1
            except Exception as e:
                invalid_count += 1
                self.message_user(
                    request,
                    f'Erro no projeto {project.client_code}: {str(e)}',
                    messages.ERROR
                )
        
        if valid_count > 0:
            self.message_user(
                request,
                f'{valid_count} projetos validados com sucesso.',
                messages.SUCCESS
            )
        
        if invalid_count > 0:
            self.message_user(
                request,
                f'{invalid_count} projetos com problemas de validação.',
                messages.WARNING
            )
    validate_documents.short_description = "Validar documentos CPF/CNPJ"


@admin.register(ConsumerUnit)
class ConsumerUnitAdmin(admin.ModelAdmin):
    list_display = ('client_code', 'project', 'percentage')
    list_filter = ('project__client_type', 'project__project_class')
    search_fields = ('client_code', 'project__client_code', 'project__project_holder_name')
    ordering = ('project', 'client_code')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('project')


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'project',
        'document_type_display',
        'file_name',
        'file_type',
        'approval_status',
        'uploaded_at'
    )
    
    list_filter = (
        'document_type',
        'file_type',
        'is_approved',
        'uploaded_at',
        'project__client_type'
    )
    
    search_fields = (
        'project__client_code',
        'project__project_holder_name',
        'description'
    )
    
    ordering = ('-uploaded_at',)
    
    readonly_fields = (
        'file_type',
        'uploaded_at',
        'approved_at',
        'approved_by'
    )
    
    fieldsets = (
        ('Informações do Documento', {
            'fields': (
                'project',
                'document_type',
                'file',
                'file_type',
                'description'
            )
        }),
        ('Aprovação', {
            'fields': (
                'is_approved',
                'rejection_reason',
                'approved_at',
                'approved_by'
            )
        }),
        ('Metadados', {
            'fields': (
                'uploaded_at',
            ),
            'classes': ('collapse',)
        })
    )
    
    def document_type_display(self, obj):
        return obj.get_document_type_display()
    document_type_display.short_description = 'Tipo de Documento'
    
    def file_name(self, obj):
        if obj.file:
            return obj.file.name.split('/')[-1]
        return '-'
    file_name.short_description = 'Arquivo'
    
    def approval_status(self, obj):
        if obj.is_approved:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Aprovado</span>'
            )
        elif obj.rejection_reason:
            return format_html(
                '<span style="color: red; font-weight: bold;">✗ Rejeitado</span>'
            )
        else:
            return format_html(
                '<span style="color: orange; font-weight: bold;">⏳ Pendente</span>'
            )
    approval_status.short_description = 'Status'
    
    def save_model(self, request, obj, form, change):
        if obj.is_approved and not obj.approved_by:
            obj.approved_by = request.user
            from django.utils import timezone
            obj.approved_at = timezone.now()
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('project', 'approved_by')
    
    actions = ['approve_documents', 'reject_documents']
    
    def approve_documents(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            is_approved=True,
            approved_by=request.user,
            approved_at=timezone.now(),
            rejection_reason=''
        )
        self.message_user(
            request,
            f'{updated} documentos aprovados.',
            messages.SUCCESS
        )
    approve_documents.short_description = "Aprovar documentos selecionados"
    
    def reject_documents(self, request, queryset):
        updated = queryset.update(
            is_approved=False,
            approved_by=None,
            approved_at=None
        )
        self.message_user(
            request,
            f'{updated} documentos rejeitados. Adicione o motivo da rejeição editando cada documento.',
            messages.WARNING
        )
    reject_documents.short_description = "Rejeitar documentos selecionados"


# Customização adicional do admin site
admin.site.site_header = "Administração de Projetos Solares"
admin.site.site_title = "Admin Projetos"
admin.site.index_title = "Painel de Controle"
