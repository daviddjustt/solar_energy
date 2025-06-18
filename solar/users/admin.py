import logging
import re

# Django imports
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils.html import format_html, mark_safe
from django.conf import settings #
from django.contrib.admin.views.main import ChangeList 
from .views import exportar_usuarios_download_view

# Imports models
from .models import (
    User,
    UserImport,
    UserChangeLog,
    UserExport,
    EmailLog,
)

# Imports services
from .services import (
    UserImportService,
    UserExportService,
)

# Importar o formulário simples para renderização no Admin
from .forms import ImportUserForm

logger = logging.getLogger(__name__)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Configuração do Admin para o modelo de usuário personalizado com histórico e log de alterações."""
    
    # Adicionado 'acesso_especial_cpf' ao list_display
    list_display = ('email', 'name', 'cpf', 'patent', 'is_active', 'is_admin',
                    'is_operacoes', 'is_sac', 'sac_profile', 'acesso_especial_cpf', 'history_link')
    
    # Adicionado 'acesso_especial_cpf' aos filtros
    list_filter = ('is_active', 'is_admin', 'is_superuser', 'patent', 'is_operacoes',
                   'is_sac', 'sac_profile', 'acesso_especial_cpf')
    
    search_fields = ('email', 'name', 'cpf')
    ordering = ('email', 'name')
    readonly_fields = ('created_at', 'updated_at', 'history_button')
    list_per_page = 20
    
    # Adicionado seção de Acesso Especial aos fieldsets
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Informações Pessoais'), {'fields': ('name', 'cpf', 'celular', 'photo', 'patent')}),
        (_('Permissões'), {'fields': ('is_active', 'is_admin', 'is_superuser', 'is_operacoes',
                                      'is_sac', 'sac_profile', 'groups', 'user_permissions')}),
        (_('Acesso Especial'), {'fields': ('acesso_especial_cpf',)}),
        (_('Datas Importantes'), {'fields': ('last_login', 'created_at', 'updated_at')}),
        (_('Histórico'), {'fields': ('history_button',)}),
    )
    
    # Adicionado acesso especial aos add_fieldsets
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'cpf', 'celular', 'password', 'password2', 'patent'),
        }),
        (_('Permissões'), {
            'fields': ('is_active', 'is_admin', 'is_superuser', 'is_operacoes',
                       'is_sac', 'sac_profile', 'groups', 'user_permissions'),
        }),
        (_('Acesso Especial'), {
            'fields': ('acesso_especial_cpf',),
        }),
    )
    
    # Ações em lote
    actions = ['activate_users', 'deactivate_users']

    def history_button(self, obj):
        """Botão para acessar o histórico detalhado na página de edição."""
        if obj.pk:
            return format_html(
                '<a href="{}" class="historylink">Ver histórico completo</a>',
                reverse(f'admin:{obj._meta.app_label}_{obj._meta.model_name}_history', args=[obj.pk])
            )
        return "-"
    history_button.short_description = 'Histórico Detalhado'

    def history_link(self, obj):
        """Adiciona um link para o histórico na lista de usuários."""
        if obj.pk:
            return format_html(
                '<a href="{}" class="button">Histórico</a>',
                reverse(f'admin:{obj._meta.app_label}_{obj._meta.model_name}_history', args=[obj.pk])
            )
        return "-"
    history_link.short_description = 'Histórico'

    def save_model(self, request, obj, form, change):
        """
        Sobrescreve o método save_model para registrar as alterações de campo
        no UserChangeLog e integrar com o django-simple-history (se aplicável).
        """
        # Definir o usuário que está fazendo a alteração para registro no histórico
        if hasattr(obj, '_history_user'):
             obj._history_user = request.user

        # Registrar alterações de campo manualmente para UserChangeLog
        if change: # Apenas para alterações de objetos existentes
            try:
                # Buscar o objeto original do banco de dados antes das alterações do formulário
                original_obj = self.model.objects.get(pk=obj.pk)
                
                # Campos a serem ignorados no log
                ignored_fields = [
                    'password', 'last_login', 'created_at', 'updated_at',
                    '_history_user', 'groups', 'user_permissions', 'photo'
                ]
                
                # Iterar sobre os campos do modelo e comparar valores
                for field in self.model._meta.fields:
                    field_name = field.name
                    if field_name in ignored_fields:
                        continue
                        
                    old_value = getattr(original_obj, field_name)
                    new_value = getattr(obj, field_name)
                    
                    # Comparar valores
                    old_value_str = str(old_value) if old_value is not None else ''
                    new_value_str = str(new_value) if new_value is not None else ''
                    
                    if old_value_str != new_value_str:
                        # Cria uma entrada no log de alteração
                        UserChangeLog.objects.create(
                            user=obj,
                            changed_by=request.user,
                            field_name=field_name,
                            old_value=old_value_str,
                            new_value=new_value_str
                        )
            except self.model.DoesNotExist:
                logger.warning(f"Objeto User com PK {obj.pk} não encontrado durante o registro de log.")
            except Exception as e:
                logger.error(f"Erro ao registrar log de alteração para o usuário {obj.email}: {e}")

        # Chama o save_model original para salvar o objeto no banco de dados
        super().save_model(request, obj, form, change)

    def activate_users(self, request, queryset):
        """Ativa os usuários selecionados."""
        updated_count = 0
        for obj in queryset:
            # Registra o usuário que está realizando a alteração para o histórico
            if hasattr(obj, '_history_user'):
                 obj._history_user = request.user
            # Loga a mudança de is_active
            if not obj.is_active:
                 UserChangeLog.objects.create(
                    user=obj,
                    changed_by=request.user,
                    field_name='is_active',
                    old_value='False',
                    new_value='True'
                 )
            obj.is_active = True
            obj.save()
            updated_count += 1
        self.message_user(request, f'{updated_count} usuários foram ativados com sucesso.')
    activate_users.short_description = "Ativar usuários selecionados"

    def deactivate_users(self, request, queryset):
        """Desativa os usuários selecionados."""
        updated_count = 0
        for obj in queryset:
            # Registra o usuário que está realizando a alteração para o histórico
            if hasattr(obj, '_history_user'):
                 obj._history_user = request.user
            # Loga a mudança de is_active
            if obj.is_active:
                 UserChangeLog.objects.create(
                    user=obj,
                    changed_by=request.user,
                    field_name='is_active',
                    old_value='True',
                    new_value='False'
                 )
            obj.is_active = False
            obj.save()
            updated_count += 1
        self.message_user(request, f'{updated_count} usuários foram desativados com sucesso.')
    deactivate_users.short_description = "Desativar usuários selecionados"


@admin.register(UserExport)
class UserExportAdmin(admin.ModelAdmin):
    """
    Admin para exportação de usuários
    """
    list_display = ("email", "name", "cpf", "celular")
    search_fields = ("email", "name", "cpf", "celular")
    list_filter = ("is_active", "is_admin", "patent", "is_operacoes", "is_sac", "sac_profile")
    actions = ["export_users"]
    
    # Remover botões de adicionar e excluir
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False

    def export_users(self, request, queryset):
        """
        Ação para exportar usuários selecionados
        """
        export_service = UserExportService()
        return export_service.create_csv_response(
            queryset=queryset,
            filename="usuarios_selecionados_exportados.csv"
        )
    export_users.short_description = _("Exportar usuários selecionados para CSV")

    def get_queryset(self, request):
        """Personaliza o queryset para incluir todos os usuários"""
        return User.objects.all()

    def get_urls(self):
        """Adiciona URLs personalizadas para exportação de todos os usuários"""
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_site.admin_view(self.export_view), name='changelist'),
            path('userexport/download/', self.admin_site.admin_view(exportar_usuarios_download_view), name='users_userexport_exportar_usuarios_download'),
        ]
        return custom_urls + urls

    def export_view(self, request):
        """View para mostrar a página de exportação"""
        context = {
            **self.admin_site.each_context(request),
            'title': 'Exportação de Usuários',
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'model_name': self.model._meta.model_name,
            'export_all_url': reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_exportar_usuarios_download'),
        }
        return render(request, 'admin/export_users.html', context)

    def export_all_users(self, request):
        """
        View para exportar todos os usuários (ou filtrados pelo changelist, se acessado de lá).
        """
        export_service = UserExportService()
        try:
            cl = ChangeList(
                request,
                self.model,
                self.list_display,
                self.list_display_links,
                self.list_filter,
                self.date_hierarchy,
                self.search_fields,
                self.list_select_related,
                self.list_per_page,
                self.list_max_show_all,
                self.list_editable,
                self,
            )
            queryset = cl.queryset
            filename = "usuarios_filtrados_exportados.csv" if request.GET else "todos_usuarios.csv"
        except Exception as e:
            logger.error(f"Error processing ChangeList for export, exporting all users. Error: {e}")
            queryset = self.get_queryset(request)
            filename = "todos_usuarios_fallback.csv"
            self.message_user(request, _("Não foi possível aplicar filtros de lista. Exportando todos os usuários."), messages.WARNING)
        
        return export_service.create_csv_response(
            queryset=queryset,
            filename=filename
        )

    def changelist_view(self, request, extra_context=None):
        """
        Redireciona para a página de exportação ao invés de mostrar a lista,
        a menos que filtros ou busca estejam aplicados.
        """
        query_params = request.GET.copy()
        internal_params_to_ignore = ['p', 'o']
        for param in internal_params_to_ignore:
             if param in query_params:
                 del query_params[param]
        
        if query_params:
            return super().changelist_view(request, extra_context)
        
        return redirect(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist')


@admin.register(UserImport)
class UserImportAdmin(admin.ModelAdmin):
    model = UserImport
    
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_view_permission(self, request, obj=None):
        return True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_site.admin_view(self.import_view), name='changelist'),
        ]
        return custom_urls + urls

    def import_view(self, request):
        """
        View para mostrar o formulário de importação e processar o arquivo.
        """
        imported_users_list = []
        email_errors = []
        errors = []
        show_result_table = False
        
        mailhog_url = settings.MAILHOG_URL if hasattr(settings, 'MAILHOG_URL') else "http://localhost:8025"
        if settings.DEBUG:
             self.message_user(
                 request,
                 mark_safe(f'Você pode verificar os emails enviados em: <a href="{mailhog_url}" target="_blank">MailHog</a>'),
                 messages.INFO
             )

        if request.method == 'POST':
            form = ImportUserForm(request.POST, request.FILES)
            if form.is_valid():
                file_obj = form.cleaned_data['file']
                send_emails = form.cleaned_data.get('send_emails', True)
                
                import_service = UserImportService(file_obj, admin_user=request.user)
                import_result_dict = import_service.import_users(send_emails=send_emails)
                
                success = import_result_dict.get('success', False)
                errors = import_result_dict.get('errors', [])
                imported_users_list = import_result_dict.get('imported_users', [])
                email_errors = import_result_dict.get('email_errors', [])

                if success:
                    success_message = import_result_dict.get('message', 'Importação concluída.')
                    self.message_user(request, success_message, messages.SUCCESS)
                    
                    if errors:
                         for error_detail in errors:
                             error_msg = f"Linha {error_detail.get('row', 'N/A')}: {error_detail.get('identifier', 'N/A')} - {error_detail.get('error', 'Erro desconhecido')}"
                             self.message_user(request, error_msg, messages.ERROR)
                    
                    if email_errors:
                         for email_error_detail in email_errors:
                             email_error_msg = f"Falha no envio de email para {email_error_detail.get('recipient', 'N/A')}: {email_error_detail.get('error', 'Erro desconhecido')}"
                             self.message_user(request, email_error_msg, messages.WARNING)
                    
                    if imported_users_list or errors or email_errors:
                         show_result_table = True
                    else:
                         return HttpResponseRedirect(reverse('admin:users_user_changelist'))
                else:
                    general_error_message = import_result_dict.get('message', 'Ocorreu um erro geral durante a importação.')
                    self.message_user(request, general_error_message, messages.ERROR)
                    
                    if errors:
                         for error_detail in errors:
                             error_msg = f"Linha {error_detail.get('row', 'N/A')}: {error_detail.get('identifier', 'N/A')} - {error_detail.get('error', 'Erro desconhecido')}"
                             self.message_user(request, error_msg, messages.ERROR)
                    
                    if email_errors:
                         for email_error_detail in email_errors:
                             email_error_msg = f"Falha no envio de email para {email_error_detail.get('recipient', 'N/A')}: {email_error_detail.get('error', 'Erro desconhecido')}"
                             self.message_user(request, email_error_msg, messages.WARNING)
                    
                    show_result_table = True
        else:
            form = ImportUserForm()

        adminform = helpers.AdminForm(form, [(None, {'fields': list(form.fields.keys())})], {})
        context = {
            **self.admin_site.each_context(request),
            'title': _('Importação de Usuários'),
            'adminform': adminform,
            'form': form,
            'opts': self.model._meta,
            'original': None,
            'change': False,
            'add': False,
            'is_popup': False,
            'save_as': False,
            'has_delete_permission': self.has_delete_permission(request),
            'has_add_permission': self.has_add_permission(request),
            'has_change_permission': self.has_change_permission(request),
            'has_view_permission': self.has_view_permission(request),
            'has_editable_inline_admin_formsets': False,
            'media': self.media + form.media,
            'form_url': '',
            'show_save': True,
            'show_save_and_continue': False,
            'imported_users': imported_users_list,
            'errors': errors,
            'email_errors': email_errors,
            'show_result_table': show_result_table,
            'app_label': self.model._meta.app_label,
            'model_name': self.model._meta.model_name,
        }
        return render(request, 'admin/import_form.html', context)


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """Admin para o modelo EmailLog."""
    list_display = ('user', 'email_type', 'recipient', 'status', 'sent_at')
    list_filter = ('email_type', 'status', 'sent_at')
    search_fields = [
        'user__name',
        'user__email',
        'recipient',
        'subject',
        'error_message',
    ]
    readonly_fields = (
        'user',
        'email_type',
        'recipient',
        'subject',
        'status',
        'sent_at',
        'error_message',
    )
    date_hierarchy = 'sent_at'
    
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UserChangeLog)
class UserChangeLogAdmin(admin.ModelAdmin):
    """Admin para o modelo UserChangeLog com exibição de valores antigo e novo."""
    list_display = ['user', 'changed_by', 'field_name', 'old_value', 'new_value', 'changed_at']
    list_filter = ['field_name', 'changed_at']
    search_fields = [
        'user__name',
        'user__email',
        'user__cpf',
        'changed_by__name',
        'changed_by__email',
        'field_name',
        'old_value',
        'new_value',
    ]
    readonly_fields = (
        'user',
        'changed_by',
        'field_name',
        'old_value',
        'new_value',
        'changed_at',
    )
    date_hierarchy = 'changed_at'
    
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False
