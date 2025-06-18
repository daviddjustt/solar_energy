from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from arcanosig.oper.models import (
    Operacao, Guarnicao, GuarnicaoMembro,
    Veiculo, FotoVeiculo, Abastecimento,
    CautelaIndividual, ItemCautela, AceiteCautela,
    Notificacao
)
from django.contrib.admin import TabularInline


# Base para otimizar select_related
class BaseSelectRelatedAdmin(admin.ModelAdmin):
    list_select_related = ()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.list_select_related:
            qs = qs.select_related(*self.list_select_related)
        return qs


# Inlines
class GuarnicaoInline(TabularInline):
    model = Guarnicao
    extra = 0
    fields = ('name', 'comandante', 'veiculo')
    verbose_name = _("Guarnição")
    verbose_name_plural = _("Guarnições")


class GuarnicaoMembroInline(TabularInline):
    model = GuarnicaoMembro
    extra = 0
    fields = ('user',)
    verbose_name = _("Membro")
    verbose_name_plural = _("Membros")


class ItemCautelaInline(TabularInline):
    model = ItemCautela
    extra = 0
    fields = (
        'tipo_equipamento', 'numero_serie',
        'quantidade', 'status_equipamento', 'data_devolucao'
    )
    readonly_fields = ('data_devolucao',)
    verbose_name = _("Item de Cautela")
    verbose_name_plural = _("Itens de Cautela")


class AceiteCautelaInline(TabularInline):
    model = AceiteCautela
    extra = 0
    fields = ('protocolo', 'status', 'data_aceite', 'ip_aceite')
    readonly_fields = ('protocolo', 'data_aceite', 'ip_aceite')
    verbose_name = _("Aceite de Cautela")
    verbose_name_plural = _("Aceites de Cautela")


class AbastecimentoInline(TabularInline):
    model = Abastecimento
    extra = 0
    fields = ('data', 'km_atual', 'litros', 'valor_total')
    verbose_name = _("Abastecimento")
    verbose_name_plural = _("Abastecimentos")


class FotoVeiculoInline(TabularInline):
    model = FotoVeiculo
    extra = 0
    verbose_name = _("Foto do Veículo")
    verbose_name_plural = _("Fotos do Veículo")


# Operação
@admin.register(Operacao)
class OperacaoAdmin(BaseSelectRelatedAdmin):
    list_display = ('id', 'name', 'start_date', 'end_date', 'is_active', 'created_at')
    list_filter = ('is_active', 'start_date')
    search_fields = ('name', 'description')
    date_hierarchy = 'start_date'
    ordering = ('-start_date',)
    fieldsets = (
        (None, {'fields': ('name', 'description', 'is_active')}),
        (_('Datas'), {'fields': ('start_date', 'end_date')}),
    )
    inlines = [GuarnicaoInline]


# Guarnição
@admin.register(Guarnicao)
class GuarnicaoAdmin(BaseSelectRelatedAdmin):
    list_display = ('id', 'name', 'operacao', 'comandante', 'veiculo', 'created_at')
    list_filter = ('operacao__is_active', 'operacao')
    search_fields = ('name', 'comandante__name', 'operacao__name')
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('name', 'operacao', 'comandante', 'veiculo')}),
    )
    inlines = [GuarnicaoMembroInline]

    list_select_related = ('operacao', 'comandante', 'veiculo')


# Membro de guarnição
@admin.register(GuarnicaoMembro)
class GuarnicaoMembroAdmin(BaseSelectRelatedAdmin):
    list_display = ('id', 'user', 'guarnicao', 'created_at')
    list_filter = ('guarnicao__operacao',)
    search_fields = ('user__name', 'guarnicao__name')
    ordering = ('-created_at',)
    raw_id_fields = ('user', 'guarnicao')

    list_select_related = ('user', 'guarnicao', 'guarnicao__operacao')


# Veículo
@admin.register(Veiculo)
class VeiculoAdmin(BaseSelectRelatedAdmin):
    list_display = ('id', 'placa', 'modelo', 'em_condicao', 'km_atual', 'created_at')
    list_filter = ('modelo', 'em_condicao')
    search_fields = ('placa', 'observacao')
    ordering = ('placa',)
    fieldsets = (
        (None, {'fields': ('placa', 'modelo', 'km_atual')}),
        (_('Status'), {'fields': ('em_condicao', 'observacao')}),
    )
    inlines = [AbastecimentoInline, FotoVeiculoInline]

    # não precisa de select_related aqui


@admin.register(Abastecimento)
class AbastecimentoAdmin(BaseSelectRelatedAdmin):
    list_display = ('id', 'veiculo', 'data', 'km_atual', 'litros', 'valor_total')
    list_filter = ('veiculo', 'data')
    search_fields = ('veiculo__placa', 'observacao')
    date_hierarchy = 'data'
    ordering = ('-data',)
    fieldsets = (
        (None, {'fields': ('veiculo', 'data')}),
        (_('Detalhes'), {'fields': ('km_atual', 'litros', 'valor_total', 'observacao')}),
    )
    raw_id_fields = ('veiculo',)

    list_select_related = ('veiculo',)


@admin.register(CautelaIndividual)
class CautelaIndividualAdmin(BaseSelectRelatedAdmin):
    list_display = (
        'id', 'policial', 'guarnicao',
        'data_entrega', 'data_devolucao', 'aceite_status'
    )
    list_filter = ('aceite_status', 'data_entrega', 'guarnicao__operacao')
    search_fields = ('policial__name', 'protocolo_aceite', 'guarnicao__name')
    date_hierarchy = 'data_entrega'
    ordering = ('-data_entrega',)
    readonly_fields = ('aceite_status', 'protocolo_aceite', 'data_hora_aceite')
    fieldsets = (
        (None, {'fields': ('policial', 'guarnicao', 'data_entrega')}),
        (_('Devolução'), {'fields': ('data_devolucao', 'observacao_devolucao')}),
        (_('Aceite'), {
            'fields': ('aceite_status', 'protocolo_aceite', 'data_hora_aceite'),
            'classes': ('collapse',)
        }),
    )
    inlines = [ItemCautelaInline, AceiteCautelaInline]
    raw_id_fields = ('policial', 'guarnicao')

    list_select_related = ('policial', 'guarnicao', 'guarnicao__operacao')


@admin.register(ItemCautela)
class ItemCautelaAdmin(BaseSelectRelatedAdmin):
    list_display = (
        'id', 'tipo_equipamento', 'numero_serie',
        'quantidade', 'cautela', 'data_devolucao', 'status_equipamento'
    )
    list_filter = ('tipo_equipamento', 'status_equipamento', 'data_devolucao')
    search_fields = ('numero_serie', 'cautela__policial__name')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    fieldsets = (
        (None, {
            'fields': ('cautela', 'tipo_equipamento', 'numero_serie', 'quantidade')
        }),
        (_('Devolução'), {
            'fields': (
                'data_devolucao', 'status_equipamento',
                'descricao_danos', 'protocolo_devolucao', 'observacao'
            )
        }),
    )
    raw_id_fields = ('cautela',)

    list_select_related = ('cautela', 'cautela__policial')


@admin.register(AceiteCautela)
class AceiteCautelaAdmin(BaseSelectRelatedAdmin):
    list_display = ('id', 'protocolo', 'cautela', 'status', 'data_aceite', 'created_at')
    list_filter = ('status', 'data_aceite')
    search_fields = ('protocolo', 'cautela__policial__name', 'observacao')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('protocolo', 'data_aceite', 'ip_aceite')
    fieldsets = (
        (None, {'fields': ('cautela', 'protocolo', 'status')}),
        (_('Detalhes do Aceite'), {
            'fields': ('data_aceite', 'ip_aceite', 'observacao')
        }),
    )
    raw_id_fields = ('cautela',)

    list_select_related = ('cautela', 'cautela__policial')


# Notificações
@admin.register(Notificacao)
class NotificacaoAdmin(BaseSelectRelatedAdmin):
    list_display = ('id', 'titulo', 'usuario', 'tipo', 'lida', 'created_at')
    list_filter = ('tipo', 'lida', 'created_at')
    search_fields = ('titulo', 'mensagem', 'usuario__name')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('usuario', 'titulo', 'mensagem', 'tipo')}),
        (_('Status'), {'fields': ('lida', 'data_leitura', 'link')}),
    )
    raw_id_fields = ('usuario',)

    list_select_related = ('usuario',)

    actions = ['mark_as_read', 'mark_as_unread']

    def mark_as_read(self, request, queryset):
        updated = queryset.update(lida=True, data_leitura=timezone.now())
        self.message_user(
            request,
            _("{} notificações marcadas como lidas.").format(updated)
        )
    mark_as_read.short_description = _("Marcar selecionadas como lidas")

    def mark_as_unread(self, request, queryset):
        updated = queryset.update(lida=False, data_leitura=None)
        self.message_user(
            request,
            _("{} notificações marcadas como não lidas.").format(updated)
        )
    mark_as_unread.short_description = _("Marcar selecionadas como não lidas")
