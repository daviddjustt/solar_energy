from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count
from django.contrib import messages
from django.utils import timezone
from .models import ClientProject, ConsumerUnit, ProjectDocument


class ConsumerUnitInline(admin.TabularInline):
    model = ConsumerUnit
    extra = 1
    fields = ('client_code', 'percentage', 'voltage')  # ADICIONADO: voltage
    verbose_name = "Unidade Consumidora"
    verbose_name_plural = "Unidades Consumidoras"


class ProjectDocumentInline(admin.StackedInline):
    model = ProjectDocument
    extra = 0
    fields = (
        'document_type', 'file', 'file_name', 'file_size', 'file_type', 
        'description', 'is_approved', 'rejection_reason'
    )  # ADICIONADO: file_name, file_size
    readonly_fields = ('file_type', 'file_name', 'file_size', 'uploaded_at')
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
        'documento_display',
        'voltage',  # ADICIONADO
        'documentation_status',
        'consumer_units_count',
        'documents_count',
        'created_at'
    )
    
    list_filter = (
        'client_type',
        'documentation_complete',
        'project_class',
        'voltage',  # ADICIONADO
        'created_at',
        'created_by'  # ADICIONADO
    )
    
    search_fields = (
        'client_code',
        'project_holder_name',
        'email',
        'documento',
        'phone',
        'city',  # ADICIONADO
        'neighborhood'  # ADICIONADO
    )
    
    ordering = ('-created_at',)
    
    readonly_fields = (
        'created_at',
        'updated_at',
        'documentation_complete',
        'created_by',
        'documento_tipo',
        'documento_label',
        'documento_validation_status',  # NOVO: mostra se documento é válido
        'coordinates_display'  # NOVO: mostra coordenadas formatadas
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
                'documento_tipo',
                'documento_label',
                'documento_validation_status',  # NOVO
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
                ('latitude', 'longitude'),
                'coordinates_display',  # NOVO
                ('lat_degrees', 'lat_minutes', 'lat_seconds'),  # NOVO
                ('long_degrees', 'long_minutes', 'long_seconds')  # NOVO
            ),
            'description': 'Coordenadas em formato decimal e graus/minutos/segundos'
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
            # ADICIONADO: ícone de validação
            is_valid = obj.is_documento_valid()
            icon = '✓' if is_valid else '✗'
            icon_color = 'green' if is_valid else 'red'
            
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}: {}</span> '
                '<span style="color: {}; font-weight: bold;">{}</span>',
                cor, tipo, obj.documento, icon_color, icon
            )
        return '-'
    documento_display.short_description = 'Documento'
    
    def documento_validation_status(self, obj):
        """NOVO: Mostra status de validação do documento"""
        if obj.documento:
            is_valid = obj.is_documento_valid()
            if is_valid:
                return format_html(
                    '<span style="color: green; font-weight: bold;">✓ Válido</span>'
                )
            else:
                return format_html(
                    '<span style="color: red; font-weight: bold;">✗ Inválido</span>'
                )
        return '-'
    documento_validation_status.short_description = 'Validação do Documento'
    
    def coordinates_display(self, obj):
        """NOVO: Exibe coordenadas formatadas"""
        if obj.latitude and obj.longitude:
            return format_html(
                '<strong>Decimal:</strong> {}, {}<br>'
                '<strong>Graus:</strong> {}°{}\'{}\" / {}°{}\'{}\"',
                obj.latitude, obj.longitude,
                obj.lat_degrees or 0, obj.lat_minutes or 0, obj.lat_seconds or 0,
                obj.long_degrees or 0, obj.long_minutes or 0, obj.long_seconds or 0
            )
        return '-'
    coordinates_display.short_description = 'Coordenadas'
    
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
        required = len(obj.get_required_documents())  # NOVO: mostra documentos obrigatórios
        
        if total > 0:
            return format_html(
                '<span style="color: {};">{}/{} docs</span><br>'
                '<small>({} obrigatórios)</small>',
                'green' if approved == total and total >= required else 'orange',
                approved, total, required
            )
        return f'0 docs ({required} obrigatórios)'
    documents_count.short_description = 'Documentos'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Se está criando um novo objeto
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'consumer_units', 'documents'
        ).select_related('created_by')
    
    actions = [
        'check_documentation', 
        'mark_documentation_complete', 
        'validate_documents',
        'convert_coordinates'  # NOVO
    ]
    
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
        """Valida documentos CPF/CNPJ"""
        valid_count = 0
        invalid_count = 0
        
        for project in queryset:
            try:
                project.full_clean()
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
    
    def convert_coordinates(self, request, queryset):
        """NOVO: Converte coordenadas entre decimal e graus/min/seg"""
        updated = 0
        for project in queryset:
            try:
                if project.latitude and project.longitude:
                    project.convert_coordinates_to_dms()
                    project.save()
                    updated += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Erro ao converter coordenadas do projeto {project.client_code}: {str(e)}',
                    messages.ERROR
                )
        
        self.message_user(
            request,
            f'{updated} projetos tiveram suas coordenadas convertidas.',
            messages.SUCCESS
        )
    convert_coordinates.short_description = "Converter coordenadas para graus/min/seg"


@admin.register(ConsumerUnit)
class ConsumerUnitAdmin(admin.ModelAdmin):
    list_display = ('client_code', 'project', 'percentage', 'voltage')  # ADICIONADO: voltage
    list_filter = (
        'project__client_type', 
        'project__project_class',
        'voltage'  # ADICIONADO
    )
    search_fields = (
        'client_code', 
        'project__client_code', 
        'project__project_holder_name'
    )
    ordering = ('project', 'client_code')
    
    fieldsets = (
        ('Informações da Unidade', {
            'fields': (
                'project',
                'client_code',
                'percentage',
                'voltage'  # ADICIONADO
            )
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('project')


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'project',
        'document_type_display',
        'file_display',  # MELHORADO
        'file_size_display',  # NOVO
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
        'file_name',  # ADICIONADO
        'description'
    )
    
    ordering = ('-uploaded_at',)
    
    readonly_fields = (
        'file_type',
        'file_name',  # ADICIONADO
        'file_size',  # ADICIONADO
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
                'file_name',  # ADICIONADO
                'file_size',  # ADICIONADO
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
    
    def file_display(self, obj):
        """MELHORADO: Exibe nome do arquivo com link"""
        if obj.file:
            file_name = obj.file_name or obj.file.name.split('/')[-1]
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                obj.file.url,
                file_name
            )
        return '-'
    file_display.short_description = 'Arquivo'
    
    def file_size_display(self, obj):
        """NOVO: Exibe tamanho do arquivo formatado"""
        if obj.file_size:
            if obj.file_size < 1024:
                return f'{obj.file_size} B'
            elif obj.file_size < 1024**2:
                return f'{obj.file_size/1024:.1f} KB'
            elif obj.file_size < 1024**3:
                return f'{obj.file_size/(1024**2):.1f} MB'
            else:
                return f'{obj.file_size/(1024**3):.1f} GB'
        return '-'
    file_size_display.short_description = 'Tamanho'
    
    def approval_status(self, obj):
        if obj.is_approved:
            approved_info = f' por {obj.approved_by}' if obj.approved_by else ''
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Aprovado</span><br>'
                '<small>{}{}</small>',
                obj.approved_at.strftime('%d/%m/%Y %H:%M') if obj.approved_at else '',
                approved_info
            )
        elif obj.rejection_reason:
            return format_html(
                '<span style="color: red; font-weight: bold;">✗ Rejeitado</span><br>'
                '<small>{}</small>',
                obj.rejection_reason[:50] + '...' if len(obj.rejection_reason) > 50 else obj.rejection_reason
            )
        else:
            return format_html(
                '<span style="color: orange; font-weight: bold;">⏳ Pendente</span>'
            )
    approval_status.short_description = 'Status'
    
    def save_model(self, request, obj, form, change):
        if obj.is_approved and not obj.approved_by:
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
        elif not obj.is_approved:
            obj.approved_by = None
            obj.approved_at = None
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('project', 'approved_by')
    
    actions = ['approve_documents', 'reject_documents', 'download_documents']
    
    def approve_documents(self, request, queryset):
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
    
    def download_documents(self, request, queryset):
        """NOVO: Action para download de documentos"""
        # Esta é uma implementação básica - você pode expandir para criar um ZIP
        count = queryset.count()
        self.message_user(
            request,
            f'{count} documentos selecionados para download. '
            'Implemente a lógica de download conforme necessário.',
            messages.INFO
        )
    download_documents.short_description = "Baixar documentos selecionados"


# Customização adicional do admin site
admin.site.site_header = "Administração de Projetos Solares"
admin.site.site_title = "Admin Projetos Solares"
admin.site.index_title = "Painel de Controle de Projetos"

# NOVO: Estatísticas personalizadas no admin
def get_admin_stats():
    """Função para obter estatísticas para o dashboard"""
    from django.db.models import Count, Q
    
    stats = {
        'total_projects': ClientProject.objects.count(),
        'complete_documentation': ClientProject.objects.filter(documentation_complete=True).count(),
        'pending_approvals': ProjectDocument.objects.filter(is_approved=False).count(),
        'total_documents': ProjectDocument.objects.count(),
    }
    return stats
