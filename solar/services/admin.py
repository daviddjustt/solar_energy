from django.contrib import admin
from django.contrib.auth import get_user_model

User = get_user_model()

# Criamos um Proxy Model dinâmico apenas para o painel Admin
class Externo(User):
    class Meta:
        proxy = True
        verbose_name = 'Parceiro Externo'
        verbose_name_plural = 'Parceiros Externos'

@admin.register(Externo)
class ExternoAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'is_active')
    list_filter = ('is_active', 'tipos_servico')
    filter_horizontal = ('tipos_servico',)
    search_fields = ('name', 'email', 'cpf')

    def get_queryset(self, request):
        """Filtra para mostrar apenas os usuários marcados como externos"""
        return super().get_queryset(request).filter(is_externo=True)