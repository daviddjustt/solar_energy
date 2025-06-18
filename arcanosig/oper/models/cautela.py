import uuid

# Django Core
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import GenericIPAddressField
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Local Apps - Models
from arcanosig.oper.models.base import BaseModel
from arcanosig.oper.models.enums import TipoEquipamento, StatusEquipamento, StatusAceite
from arcanosig.oper.models.operacao import Guarnicao, GuarnicaoMembro
from arcanosig.users.models import User


class CautelaIndividual(BaseModel):
    """
    Modelo para registrar cautelas de equipamentos individuais para policiais.
    
    Uma cautela individual representa a entrega de equipamentos para um policial
    específico, vinculado a uma guarnição e operação.
    """
    

    # FIELDS

    
    policial = models.ForeignKey(
        User,
        verbose_name=_("Policial"),
        on_delete=models.PROTECT,
        related_name="cautelas_individuais",
        limit_choices_to={'is_active': True},
        help_text=_("Policial responsável pela cautela dos equipamentos"),
    )
    
    guarnicao = models.ForeignKey(
        Guarnicao,
        verbose_name=_("Guarnição"),
        on_delete=models.PROTECT,
        related_name="cautelas_guarnicao",
        help_text=_("Guarnição à qual o policial está associado para esta cautela"),
    )
    
    data_entrega = models.DateTimeField(
        verbose_name=_("Data de Entrega dos Equipamentos"),
        default=timezone.now,
        help_text=_("Data e hora da entrega dos equipamentos para o policial"),
    )
    
    data_devolucao = models.DateTimeField(
        verbose_name=_("Data de Devolução"),
        blank=True,
        null=True,
        help_text=_("Data e hora da devolução dos equipamentos"),
    )
    
    observacao_devolucao = models.TextField(
        verbose_name=_("Observação na Devolução"),
        blank=True,
        help_text=_("Observações gerais sobre a devolução dos equipamentos"),
    )
    

    # CONTROLE DE ACEITE

    
    aceite_status = models.CharField(
        verbose_name=_("Status do Aceite"),
        max_length=15,
        choices=StatusAceite.choices,
        default=StatusAceite.PENDENTE,
        editable=False,
        help_text=_("Status atual do aceite da cautela pelo policial"),
    )
    
    protocolo_aceite = models.CharField(
        verbose_name=_("Protocolo de Aceite"),
        max_length=50,
        blank=True,
        editable=False,
        help_text=_("Protocolo único gerado para o aceite"),
    )
    
    data_hora_aceite = models.DateTimeField(
        verbose_name=_("Data do Aceite"),
        null=True,
        blank=True,
        editable=False,
        help_text=_("Data e hora em que o aceite foi confirmado"),
    )

    class Meta:
        verbose_name = _("Cautela Individual")
        verbose_name_plural = _("Cautelas Individuais")
        ordering = ['-data_entrega']
        indexes = [
            models.Index(fields=['policial', 'data_entrega']),
            models.Index(fields=['guarnicao', 'data_entrega']),
            models.Index(fields=['aceite_status']),
        ]


    # STRING REPRESENTATION

    
    def __str__(self) -> str:
        return f"Cautela de {self.policial.name} ({self.data_entrega.strftime('%d/%m/%Y')})"


    # PROPERTIES

    
    @property
    def status(self):
        """Retorna o status atual da cautela baseado na devolução."""
        if self.data_devolucao:
            return _("Devolvida")
        return _("Em uso")
    
    @property
    def aceite_completo(self):
        """Verifica se o aceite foi confirmado pelo policial."""
        return self.aceite_status == StatusAceite.CONFIRMADO
    
    @property
    def dias_em_uso(self):
        """Calcula quantos dias a cautela está em uso."""
        data_fim = self.data_devolucao or timezone.now()
        return (data_fim - self.data_entrega).days


    # VALIDATION METHODS

    
    def clean(self):
        """Validações adicionais para a cautela."""
        super().clean()
        
        self._validate_datas()
        self._validate_cautela_ativa()
        self._validate_membro_guarnicao()
        self._validate_operacao_ativa()
    
    def _validate_datas(self):
        """Valida as datas de entrega e devolução."""
        if (self.data_devolucao and self.data_entrega 
            and self.data_devolucao < self.data_entrega):
            raise ValidationError(
                _("Data de devolução não pode ser anterior à data de entrega.")
            )
    
    def _validate_cautela_ativa(self):
        """Valida se o policial já possui uma cautela ativa."""
        if not self.pk and not self.data_devolucao:
            cautelas_ativas = CautelaIndividual.objects.filter(
                policial=self.policial,
                data_devolucao__isnull=True
            ).exists()
            
            if cautelas_ativas:
                raise ValidationError(
                    _("O policial já possui uma cautela ativa. "
                      "É necessário devolver a anterior antes de criar uma nova.")
                )
    
    def _validate_membro_guarnicao(self):
        """Valida se o policial é membro da guarnição."""
        if self.policial and self.guarnicao:
            is_membro = GuarnicaoMembro.objects.filter(
                guarnicao=self.guarnicao,
                user=self.policial
            ).exists()
            
            if not is_membro:
                raise ValidationError(
                    _("O policial deve ser membro da guarnição para receber uma cautela.")
                )
    
    def _validate_operacao_ativa(self):
        """Valida se a operação da guarnição está ativa."""
        if self.guarnicao and not self.guarnicao.operacao.is_active:
            raise ValidationError(
                _("Só é possível criar cautelas para guarnições de operações ativas.")
            )


class ItemCautela(BaseModel):
    """
    Modelo para itens incluídos em uma cautela.
    
    Representa equipamentos individuais (armas, munições, tablets, rádios)
    que fazem parte de uma cautela individual.
    """
    

    # FIELDS

    
    cautela = models.ForeignKey(
        CautelaIndividual,
        verbose_name=_("Cautela"),
        on_delete=models.CASCADE,
        related_name="itens",
        help_text=_("Cautela à qual este item pertence"),
    )
    
    tipo_equipamento = models.CharField(
        verbose_name=_("Tipo de Equipamento"),
        max_length=20,
        choices=TipoEquipamento.choices,
        blank=True,
        null=True,
        help_text=_("Categoria do equipamento cautelado"),
    )
    
    numero_serie = models.CharField(
        verbose_name=_("Número de Série"),
        max_length=50,
        blank=True,
        help_text=_("Número de série ou identificação única do equipamento"),
    )
    
    quantidade = models.PositiveIntegerField(
        verbose_name=_("Quantidade"),
        default=1,
        help_text=_("Quantidade de itens deste tipo"),
    )


    # CONTROLE DE DEVOLUÇÃO

    
    data_devolucao = models.DateTimeField(
        verbose_name=_("Data de Devolução"),
        null=True,
        blank=True,
        help_text=_("Data e hora da devolução do item"),
    )
    
    status_equipamento = models.CharField(
        verbose_name=_("Status do Equipamento"),
        max_length=20,
        choices=StatusEquipamento.choices,
        default=StatusEquipamento.EM_CONDICOES,
        help_text=_("Condição do equipamento no momento da devolução"),
    )
    
    descricao_danos = models.TextField(
        verbose_name=_("Descrição dos Danos"),
        blank=True,
        help_text=_("Descreva os danos encontrados no equipamento durante a devolução"),
    )
    
    devolucao_confirmada = models.BooleanField(
        verbose_name=_("Devolução Confirmada"),
        default=False,
        help_text=_("Indica se a devolução foi confirmada pelo responsável"),
    )
    
    protocolo_devolucao = models.CharField(
        verbose_name=_("Protocolo de Devolução"),
        max_length=50,
        blank=True,
        help_text=_("Protocolo único gerado para a devolução"),
    )
    
    observacao = models.TextField(
        verbose_name=_("Observações"),
        blank=True,
        help_text=_("Observações adicionais sobre o item"),
    )

    class Meta:
        verbose_name = _("Item de Cautela")
        verbose_name_plural = _("Itens de Cautela")
        ordering = ['tipo_equipamento', 'numero_serie']
        indexes = [
            models.Index(fields=['cautela', 'tipo_equipamento']),
            models.Index(fields=['numero_serie']),
            models.Index(fields=['status_equipamento']),
        ]


    # STRING REPRESENTATION

    
    def __str__(self) -> str:
        tipo_display = self.get_tipo_equipamento_display() if self.tipo_equipamento else "Item"
        identificacao = self.numero_serie or f"Qtd: {self.quantidade}"
        return f"{tipo_display} - {identificacao}"


    # VALIDATION METHODS

    
    def clean(self):
        """Validações adicionais para o item de cautela."""
        super().clean()
        
        self._validate_numero_serie_armas()
        self._validate_cautela_devolvida()
        self._validate_descricao_danos()
    
    def _validate_numero_serie_armas(self):
        """Valida se armas possuem número de série."""
        armas = [
            TipoEquipamento.PISTOLA,
            TipoEquipamento.FUZIL,
            TipoEquipamento.CARABINA
        ]
        
        if self.tipo_equipamento in armas and not self.numero_serie:
            raise ValidationError(
                _("O número de série é obrigatório para armas.")
            )
    
    def _validate_cautela_devolvida(self):
        """Valida se é possível adicionar itens a cautela devolvida."""
        if (self.cautela and self.cautela.data_devolucao and not self.pk):
            raise ValidationError(
                _("Não é possível adicionar itens a uma cautela já devolvida.")
            )
    
    def _validate_descricao_danos(self):
        """Valida se equipamentos danificados possuem descrição."""
        status_com_danos = [StatusEquipamento.DANIFICADO, StatusEquipamento.INOPERANTE]
        
        if (self.status_equipamento in status_com_danos and not self.descricao_danos):
            raise ValidationError(
                _("É necessário descrever os danos quando o equipamento "
                  "está danificado ou inoperante.")
            )


    # BUSINESS METHODS

    
    def registrar_devolucao(self, status=StatusEquipamento.EM_CONDICOES, descricao_danos=""):
        """
        Registra a devolução do equipamento.
        
        Args:
            status: Status do equipamento na devolução
            descricao_danos: Descrição dos danos (se houver)
        
        Returns:
            bool: True se a devolução foi registrada com sucesso
        
        Raises:
            ValidationError: Se o equipamento já foi devolvido
        """
        if self.data_devolucao:
            raise ValidationError(_("Este equipamento já foi devolvido."))
        
        self.data_devolucao = timezone.now()
        self.status_equipamento = status
        self.descricao_danos = descricao_danos
        self.protocolo_devolucao = self._gerar_protocolo_devolucao()
        self.devolucao_confirmada = True
        self.save()
        
        return True
    
    def _gerar_protocolo_devolucao(self):
        """Gera um protocolo único para a devolução."""
        timestamp = timezone.now().strftime('%Y%m')
        unique_code = uuid.uuid4().hex[:8].upper()
        return f"DEV-{unique_code}-{timestamp}"


class AceiteCautela(BaseModel):
    """
    Modelo para registrar os aceites de cautelas pelos policiais.
    
    Mantém o histórico de aceites/rejeições de cautelas, permitindo
    rastrear quando e como o policial aceitou a responsabilidade.
    """
    

    # FIELDS

    
    cautela = models.ForeignKey(
        CautelaIndividual,
        verbose_name=_("Cautela"),
        on_delete=models.CASCADE,
        related_name="historico_aceites",
        help_text=_("Cautela relacionada a este aceite"),
    )
    
    protocolo = models.CharField(
        verbose_name=_("Número de Protocolo"),
        max_length=50,
        unique=True,
        help_text=_("Protocolo único para identificação do aceite"),
    )
    
    status = models.CharField(
        verbose_name=_("Status"),
        max_length=15,
        choices=StatusAceite.choices,
        default=StatusAceite.PENDENTE,
        help_text=_("Status atual do aceite"),
    )
    
    data_aceite = models.DateTimeField(
        verbose_name=_("Data do Aceite"),
        null=True,
        blank=True,
        help_text=_("Data e hora em que o aceite foi confirmado"),
    )
    
    ip_aceite = GenericIPAddressField(
        verbose_name=_("IP do Aceite"),
        null=True,
        blank=True,
        help_text=_("Endereço IP de onde o aceite foi realizado"),
    )
    
    observacao = models.TextField(
        verbose_name=_("Observação"),
        blank=True,
        help_text=_("Observações do policial sobre o aceite"),
    )

    class Meta:
        verbose_name = _("Aceite de Cautela")
        verbose_name_plural = _("Aceites de Cautela")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['cautela', 'status']),
            models.Index(fields=['protocolo']),
            models.Index(fields=['data_aceite']),
        ]


    # STRING REPRESENTATION

    
    def __str__(self) -> str:
        return f"Aceite {self.get_status_display()} - {self.protocolo}"


    # VALIDATION METHODS

    
    def clean(self):
        """Validações adicionais para o aceite de cautela."""
        super().clean()
        self._validate_aceite_cautela_devolvida()
    
    def _validate_aceite_cautela_devolvida(self):
        """Valida se é possível confirmar aceite de cautela devolvida."""
        if (self.status == StatusAceite.CONFIRMADO and 
            self.cautela and self.cautela.data_devolucao):
            raise ValidationError(
                _("Não é possível confirmar o aceite de uma cautela já devolvida.")
            )


    # BUSINESS METHODS

    
    def confirmar_aceite(self, ip_address=None, observacao=None):
        """
        Confirma o aceite da cautela pelo policial.
        
        Args:
            ip_address: Endereço IP de onde o aceite foi realizado
            observacao: Observações do policial sobre o aceite
        
        Returns:
            bool: True se o aceite foi confirmado com sucesso
        
        Raises:
            ValidationError: Se o aceite não está pendente
        """
        if self.status != StatusAceite.PENDENTE:
            raise ValidationError(
                _("Apenas aceites pendentes podem ser confirmados.")
            )
        
        self.status = StatusAceite.CONFIRMADO
        self.data_aceite = timezone.now()
        self.ip_aceite = ip_address
        
        if observacao:
            self.observacao = observacao
        
        self.save()
        
        # Atualizar status na cautela principal
        self.cautela.aceite_status = StatusAceite.CONFIRMADO
        self.cautela.protocolo_aceite = self.protocolo
        self.cautela.data_hora_aceite = self.data_aceite
        self.cautela.save(update_fields=[
            'aceite_status', 'protocolo_aceite', 'data_hora_aceite'
        ])
        
        return True
    
    def rejeitar_aceite(self, observacao=None):
        """
        Rejeita o aceite da cautela.
        
        Args:
            observacao: Motivo da rejeição
        
        Returns:
            bool: True se a rejeição foi registrada
        """
        if self.status != StatusAceite.PENDENTE:
            raise ValidationError(
                _("Apenas aceites pendentes podem ser rejeitados.")
            )
        
        self.status = StatusAceite.REJEITADO
        self.data_aceite = timezone.now()
        
        if observacao:
            self.observacao = observacao
        
        self.save()
        
        # Atualizar status na cautela principal
        self.cautela.aceite_status = StatusAceite.REJEITADO
        self.cautela.save(update_fields=['aceite_status'])
        
        return True
