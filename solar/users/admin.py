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

# Imports models
from .models import (
    User,
    UserChangeLog,
    EmailLog,
)


logger = logging.getLogger(__name__)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Configuração do Admin para o modelo de usuário personalizado com histórico e log de alterações."""
    
    list_display = ('email', 'name', 'cpf', 'patent', 'is_active', 'is_admin',
                    'is_operacoes','history_link')
    
    list_filter = ('is_active', 'is_admin', 'is_superuser', 'patent', 'is_operacoes')
    
    search_fields = ('email', 'name', 'cpf')
    ordering = ('email', 'name')
    readonly_fields = ('created_at', 'updated_at', 'history_button')
    list_per_page = 20
    
    # Adicionado seção de Acesso Especial aos fieldsets
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Informações Pessoais'), {'fields': ('name', 'cpf', 'celular', 'photo', 'patent')}),
        (_('Permissões'), {'fields': ('is_active', 'is_admin', 'is_superuser', 'is_operacoes',
                                      'groups', 'user_permissions')}),
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
                       'groups', 'user_permissions'),
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
