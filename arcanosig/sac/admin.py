from django.contrib import admin

from .models import (
    RelatorioInteligencia,
    TipoOcorrencia,
    RelatorioInteligenciaChangeLog,
    RelatorioCompartilhamento,
    CompartilhamentoAcesso
)

from django.utils.html import format_html


@admin.register(RelatorioInteligencia)
class RelatorioInteligenciaAdmin(admin.ModelAdmin):
    list_display = ['numero','numero_ano', 'tipo', 'focal', 'analista', 'criado_em', 'visualizar_pdf_btn']
    search_fields = ['numero_ano', 'focal__name', 'analista__name']
    list_filter = ['tipo', 'criado_em']
    readonly_fields = ['numero_ano', 'quantidade_acessos', 'ultima_visualizacao']

    fieldsets = (
        (None, {
            'fields': ('numero','numero_ano', 'tipo', 'arquivo_pdf')
        }),
        ('Responsáveis', {
            'fields': ('analista', 'focal')
        }),
        ('Quantitativos de Ocorrências', {
            'fields': (
                'qtd_homicidio',
                'qtd_tentativa_homicidio',
                'qtd_latrocinio',
                'qtd_tentativa_latrocinio',
                'qtd_feminicidio',
                'qtd_tentativa_feminicidio',
                'qtd_morte_intervencao',
                'qtd_mandado_prisao',
                'qtd_encontro_cadaver',
                'qtd_apreensao_drogas',
                'qtd_apreensao_armas',
                'qtd_ocorrencia_repercussao',
                'qtd_outras_intercorrencias',
            )
        }),
    )

    # Método customizado para exibir quantitativos na lista
    def display_quantitativos(self, obj):
        """
        Exibe os quantitativos diferentes de zero de forma legível na lista.
        """
        quantitativos = obj.get_quantitativos_nao_zero()
        if not quantitativos:
            return "Nenhum quantitativo registrado"

        # Formata a exibição: "Nome (Valor), Nome (Valor)"
        display_list = [f"{data['nome']} ({data['valor']})" for codigo, data in quantitativos.items()]
        return ", ".join(display_list)

    def visualizar_pdf_btn(self, obj):
        # Botão para visualizar PDF com máscara
        return format_html(
            '<a href="/api/v1/sac/relatorios-inteligencia/{}/visualizar-pdf/" class="button" target="_blank">'
            'Visualizar PDF Mascarado</a>',
            obj.id
        )
    visualizar_pdf_btn.short_description = "Visualizar PDF"
    visualizar_pdf_btn.allow_tags = True

    display_quantitativos.short_description = 'Quantitativos' # Nome da coluna no admin


@admin.register(RelatorioInteligenciaChangeLog)
class RelatorioInteligenciaChangeLogAdmin(admin.ModelAdmin):
    """
    Configuração do Admin para o modelo RelatorioInteligenciaChangeLog.
    Para visualização dos logs de alterações.
    """
    list_display = (
        'relatorio',
        'change_type',
        'changed_by',
        'changed_at',
        'field_name',
        'old_value',
        'new_value',
        'duracao_visualizacao',
        'dispositivo',
        'navegador',
    )
    list_filter = (
        'change_type',
        'changed_by',
        'changed_at',
        'relatorio', # Permite filtrar por relatório
    )
    search_fields = (
        'relatorio__numero_ano', # Busca pelo número do relatório relacionado
        'changed_by__username',  # Busca pelo nome de usuário que fez a alteração
        'field_name',
        'old_value',
        'new_value',
    )
    readonly_fields = (
        'relatorio',
        'change_type',
        'changed_by',
        'changed_at',
        'field_name',
        'old_value',
        'new_value',
        'duracao_visualizacao',
        'dispositivo',
        'navegador',
    )
    ordering = ('-changed_at',) # Ordena os logs do mais recente para o mais antigo

    # Logs de alteração geralmente não devem ser adicionados, editados ou excluídos manualmente
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        # Considere se você quer permitir a exclusão de logs de alteração.
        # Geralmente, logs são mantidos para auditoria.
        return False # Mantenha False para evitar exclusão manual


@admin.register(RelatorioCompartilhamento)
class RelatorioCompartilhamentoAdmin(admin.ModelAdmin):
    list_display = [
        'relatorio', 'tipo', 'criado_por', 'criado_em',
        'expira_em', 'ativo', 'acessos', 'is_valido_display'
    ]
    list_filter = ['tipo', 'ativo', 'criado_em', 'expira_em']
    search_fields = ['relatorio__numero_ano', 'criado_por__name', 'token']
    readonly_fields = [
        'token', 'numero_especial', 'senha_especial',
        'criado_em', 'acessos', 'ultimo_acesso'
    ]

    def is_valido_display(self, obj):
        return obj.is_valido()
    is_valido_display.short_description = 'Válido'
    is_valido_display.boolean = True

    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editando
            return self.readonly_fields + ['tipo', 'relatorio', 'criado_por']
        return self.readonly_fields


@admin.register(CompartilhamentoAcesso)
class CompartilhamentoAcessoAdmin(admin.ModelAdmin):
    list_display = [
        'compartilhamento', 'ip_address', 'sucesso', 'acessado_em'
    ]
    list_filter = ['sucesso', 'acessado_em']
    search_fields = ['ip_address', 'compartilhamento__token']
    readonly_fields = []

    def get_readonly_fields(self, request, obj=None):
        # Retorna dinamicamente todos os campos do modelo como somente leitura
        if not self.readonly_fields:
            return [field.name for field in self.model._meta.fields]
        return self.readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
