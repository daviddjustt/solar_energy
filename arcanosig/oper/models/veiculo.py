from decimal import Decimal
from typing import Optional

# Django Core
from django.core.exceptions import ValidationError
from django.core.validators import (
    MinValueValidator,
    RegexValidator,
    FileExtensionValidator
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Local Apps
from arcanosig.oper.models.base import BaseModel
from arcanosig.oper.models.enums import ModeloVeiculo



# MANAGERS


class VeiculoManager(models.Manager):
    """Manager customizado para veículos."""
    
    def disponiveis(self):
        """Retorna veículos em condições de uso e não associados a guarnições."""
        return self.filter(
            em_condicao=True,
            guarnicao_associada__isnull=True
        )
    
    def em_uso(self):
        """Retorna veículos atualmente associados a guarnições."""
        return self.filter(guarnicao_associada__isnull=False)
    
    def manutencao(self):
        """Retorna veículos que não estão em condições de uso."""
        return self.filter(em_condicao=False)
    
    def por_modelo(self, modelo):
        """Retorna veículos filtrados por modelo."""
        return self.filter(modelo=modelo)
    
    def com_quilometragem_alta(self, limite=100000):
        """Retorna veículos com quilometragem acima do limite."""
        return self.filter(km_atual__gt=limite)


class AbastecimentoManager(models.Manager):
    """Manager customizado para abastecimentos."""
    
    def por_veiculo(self, veiculo):
        """Retorna abastecimentos de um veículo específico."""
        return self.filter(veiculo=veiculo)
    
    def por_periodo(self, data_inicio, data_fim):
        """Retorna abastecimentos em um período específico."""
        return self.filter(
            data__date__gte=data_inicio,
            data__date__lte=data_fim
        )
    
    def do_mes_atual(self):
        """Retorna abastecimentos do mês atual."""
        hoje = timezone.now().date()
        inicio_mes = hoje.replace(day=1)
        return self.filter(data__date__gte=inicio_mes)
    
    def valor_total_periodo(self, data_inicio, data_fim):
        """Calcula valor total gasto em combustível no período."""
        return self.por_periodo(data_inicio, data_fim).aggregate(
            total=models.Sum('valor_total')
        )['total'] or Decimal('0.00')



# MAIN MODELS


class Veiculo(BaseModel):
    """
    Modelo para gestão de veículos utilizados em operações policiais.
    
    Controla informações essenciais como placa, modelo, condições de uso
    e quilometragem atual, além de permitir vinculação com guarnições.
    """
    
    
    # FIELDS
    
    
    placa = models.CharField(
        verbose_name=_("Placa"),
        max_length=7,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$',
                message=_(
                    'Formato de placa inválido. '
                    'Use formato antigo (ABC1234) ou Mercosul (ABC1A23)'
                )
            )
        ],
        help_text=_(
            "Placa do veículo sem espaços ou traços. "
            "Formatos aceitos: ABC1234 ou ABC1A23"
        ),
    )
    
    modelo = models.CharField(
        verbose_name=_("Modelo"),
        max_length=20,
        choices=ModeloVeiculo.choices,
        help_text=_("Modelo do veículo conforme especificação operacional"),
    )
    
    em_condicao = models.BooleanField(
        verbose_name=_("Em condições de uso"),
        default=True,
        help_text=_(
            "Indica se o veículo está apto para uso em operações"
        ),
    )
    
    observacao = models.TextField(
        verbose_name=_("Observação"),
        blank=True,
        help_text=_(
            "Observações sobre o estado do veículo, "
            "obrigatório quando não está em condições de uso"
        ),
    )
    
    km_atual = models.PositiveIntegerField(
        verbose_name=_("Quilometragem atual"),
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Quilometragem atual do veículo em KM"),
    )
    
    data_ultima_revisao = models.DateField(
        verbose_name=_("Data da última revisão"),
        null=True,
        blank=True,
        help_text=_("Data da última revisão ou manutenção preventiva"),
    )
    
    km_proxima_revisao = models.PositiveIntegerField(
        verbose_name=_("KM da próxima revisão"),
        null=True,
        blank=True,
        help_text=_("Quilometragem programada para próxima revisão"),
    )

    # Manager
    objects = VeiculoManager()

    class Meta:
        ordering = ['placa']
        verbose_name = _("Veículo")
        verbose_name_plural = _("Veículos")
        indexes = [
            models.Index(fields=['placa']),
            models.Index(fields=['modelo']),
            models.Index(fields=['em_condicao']),
            models.Index(fields=['km_atual']),
        ]

    
    # STRING REPRESENTATION
    
    
    def __str__(self) -> str:
        return f"{self.get_modelo_display()} - {self.placa}"

    
    # PROPERTIES
    
    
    @property
    def placa_formatada(self):
        """Retorna a placa formatada com hífen."""
        if len(self.placa) == 7:
            # Formato antigo: ABC-1234
            if self.placa[3].isdigit() and self.placa[4].isdigit():
                return f"{self.placa[:3]}-{self.placa[3:]}"
            # Formato Mercosul: ABC-1A23
            else:
                return f"{self.placa[:3]}-{self.placa[3:]}"
        return self.placa
    
    @property
    def status_condicao(self):
        """Retorna o status de condição formatado."""
        return _("Apto") if self.em_condicao else _("Manutenção")
    
    @property
    def esta_associado(self):
        """Verifica se o veículo está associado a uma guarnição."""
        return hasattr(self, 'guarnicao_associada') and self.guarnicao_associada is not None
    
    @property
    def precisa_revisao(self):
        """Verifica se o veículo precisa de revisão baseado na quilometragem."""
        if self.km_proxima_revisao:
            return self.km_atual >= self.km_proxima_revisao
        return False
    
    @property
    def total_abastecimentos(self):
        """Retorna o número total de abastecimentos."""
        return self.abastecimentos.count()
    
    @property
    def ultimo_abastecimento(self):
        """Retorna o último abastecimento realizado."""
        return self.abastecimentos.first()
    
    @property
    def total_fotos(self):
        """Retorna o número total de fotos."""
        return self.fotos.count()
    
    @property
    def valor_total_combustivel_mes(self):
        """Calcula o valor total gasto em combustível no mês atual."""
        return self.abastecimentos.do_mes_atual().aggregate(
            total=models.Sum('valor_total')
        )['total'] or Decimal('0.00')

    
    # CUSTOM SAVE METHOD
    
    
    def save(self, *args, **kwargs):
        """Processa dados antes de salvar."""
        # Normaliza a placa
        if self.placa:
            self.placa = self.placa.upper().replace('-', '').replace(' ', '')
        
        # Normaliza observação
        if self.observacao:
            self.observacao = self.observacao.upper().strip()
        
        super().save(*args, **kwargs)

    
    # VALIDATION METHODS
    
    
    def clean(self):
        """Validações personalizadas do modelo."""
        super().clean()
        
        self._validate_observacao_required()
        self._validate_guarnicao_operacao()
        self._validate_unique_assignment()
        self._validate_quilometragem_revisao()
    
    def _validate_observacao_required(self):
        """Valida se observação é obrigatória quando não está em condições."""
        if not self.em_condicao and not self.observacao:
            raise ValidationError({
                'observacao': _(
                    "É necessário informar uma observação quando "
                    "o veículo não está em condições de uso."
                )
            })
    
    def _validate_guarnicao_operacao(self):
        """Valida se a guarnição associada está em operação ativa."""
        if (hasattr(self, 'guarnicao_associada') and 
            self.guarnicao_associada and
            hasattr(self.guarnicao_associada, 'operacao')):
            
            if not self.guarnicao_associada.operacao.is_active:
                raise ValidationError({
                    'guarnicao_associada': _(
                        "Só é possível vincular veículos a "
                        "guarnições de operações ativas."
                    )
                })
    
    def _validate_unique_assignment(self):
        """Valida se o veículo não está associado a outra guarnição."""
        if (hasattr(self, 'guarnicao_associada') and 
            self.guarnicao_associada and self.pk):
            
            # Importação local para evitar dependência circular
            from arcanosig.oper.models.guarnicao import Guarnicao
            
            outras_guarnicoes = Guarnicao.objects.filter(
                veiculo=self
            ).exclude(pk=self.guarnicao_associada.pk)
            
            if outras_guarnicoes.exists():
                raise ValidationError({
                    'guarnicao_associada': _(
                        "Este veículo já está associado a outra guarnição."
                    )
                })
    
    def _validate_quilometragem_revisao(self):
        """Valida quilometragem da próxima revisão."""
        if (self.km_proxima_revisao and 
            self.km_proxima_revisao <= self.km_atual):
            raise ValidationError({
                'km_proxima_revisao': _(
                    "Quilometragem da próxima revisão deve ser "
                    "maior que a quilometragem atual."
                )
            })

    
    # BUSINESS METHODS
    
    
    def atualizar_quilometragem(self, nova_km):
        """
        Atualiza a quilometragem do veículo.
        
        Args:
            nova_km (int): Nova quilometragem
            
        Raises:
            ValidationError: Se a nova quilometragem for menor que a atual
        """
        if nova_km < self.km_atual:
            raise ValidationError(
                _("Nova quilometragem não pode ser menor que a atual.")
            )
        
        self.km_atual = nova_km
        self.save(update_fields=['km_atual'])
    
    def marcar_manutencao(self, observacao):
        """
        Marca o veículo como em manutenção.
        
        Args:
            observacao (str): Motivo da manutenção
        """
        self.em_condicao = False
        self.observacao = observacao
        self.save(update_fields=['em_condicao', 'observacao'])
    
    def liberar_manutencao(self):
        """Libera o veículo da manutenção."""
        self.em_condicao = True
        self.observacao = ""
        self.save(update_fields=['em_condicao', 'observacao'])
    
    def calcular_consumo_medio(self, ultimos_abastecimentos=5):
        """
        Calcula o consumo médio baseado nos últimos abastecimentos.
        
        Args:
            ultimos_abastecimentos (int): Número de abastecimentos para cálculo
            
        Returns:
            Decimal: Consumo médio em km/l ou None se não há dados suficientes
        """
        abastecimentos = self.abastecimentos.all()[:ultimos_abastecimentos + 1]
        
        if len(abastecimentos) < 2:
            return None
        
        km_percorridos = []
        litros_consumidos = []
        
        for i in range(len(abastecimentos) - 1):
            km_diff = abastecimentos[i].km_atual - abastecimentos[i + 1].km_atual
            if km_diff > 0:
                km_percorridos.append(km_diff)
                litros_consumidos.append(abastecimentos[i].litros)
        
        if not km_percorridos:
            return None
        
        total_km = sum(km_percorridos)
        total_litros = sum(litros_consumidos)
        
        return Decimal(total_km) / total_litros if total_litros > 0 else None


class FotoVeiculo(BaseModel):
    """
    Modelo para armazenar fotos de veículos.
    
    Permite documentar o estado dos veículos, especialmente quando
    não estão em condições de uso. Limitado a 10 fotos por veículo.
    """
    
    
    # FIELDS
    
    
    veiculo = models.ForeignKey(
        Veiculo,
        verbose_name=_("Veículo"),
        on_delete=models.CASCADE,
        related_name="fotos",
        help_text=_("Veículo ao qual a foto pertence"),
    )
    
    imagem = models.ImageField(
        verbose_name=_("Imagem"),
        upload_to="veiculos/fotos/%Y/%m/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'webp']
            )
        ],
        help_text=_("Foto do veículo (formatos: jpg, jpeg, png, webp)"),
    )
    
    descricao = models.CharField(
        verbose_name=_("Descrição"),
        max_length=255,
        help_text=_("Descrição do que a foto documenta"),
    )
    
    data_foto = models.DateTimeField(
        verbose_name=_("Data da foto"),
        default=timezone.now,
        help_text=_("Data e hora em que a foto foi tirada"),
    )

    class Meta:
        verbose_name = _("Foto do Veículo")
        verbose_name_plural = _("Fotos dos Veículos")
        ordering = ['-data_foto']
        indexes = [
            models.Index(fields=['veiculo', '-data_foto']),
        ]

    
    # STRING REPRESENTATION
    
    
    def __str__(self) -> str:
        return f"Foto de {self.veiculo.placa} - {self.descricao}"

    
    # PROPERTIES
    
    
    @property
    def tamanho_formatado(self):
        """Retorna o tamanho da imagem formatado."""
        if self.imagem:
            tamanho = self.imagem.size
            if tamanho < 1024:
                return f"{tamanho} B"
            elif tamanho < 1024 * 1024:
                return f"{tamanho / 1024:.1f} KB"
            else:
                return f"{tamanho / (1024 * 1024):.1f} MB"
        return "0 B"
    
    @property
    def data_formatada(self):
        """Retorna a data formatada."""
        return self.data_foto.strftime('%d/%m/%Y %H:%M')

    
    # VALIDATION METHODS
    
    
    def clean(self):
        """Validações personalizadas do modelo."""
        super().clean()
        
        self._validate_veiculo_condicao()
        self._validate_max_fotos()
    
    def _validate_veiculo_condicao(self):
        """Valida se pode adicionar foto baseado na condição do veículo."""
        if self.veiculo and self.veiculo.em_condicao:
            raise ValidationError({
                'veiculo': _(
                    "Só é possível adicionar fotos para veículos "
                    "que não estão em condições de uso."
                )
            })
    
    def _validate_max_fotos(self):
        """Valida o limite máximo de fotos por veículo."""
        if (self.veiculo and not self.pk and 
            self.veiculo.fotos.count() >= 10):
            raise ValidationError(
                _("Limite máximo de 10 fotos por veículo atingido.")
            )

    
    # CUSTOM SAVE METHOD
    
    
    def save(self, *args, **kwargs):
        """Processa dados antes de salvar."""
        if self.descricao:
            self.descricao = self.descricao.strip()
        
        super().save(*args, **kwargs)


class Abastecimento(BaseModel):
    """
    Modelo para registrar abastecimentos de veículos.
    
    Controla informações sobre consumo de combustível, incluindo
    quilometragem, litros abastecidos e valores gastos.
    """
    
    
    # FIELDS
    
    
    veiculo = models.ForeignKey(
        Veiculo,
        verbose_name=_("Veículo"),
        on_delete=models.CASCADE,
        related_name="abastecimentos",
        help_text=_("Veículo abastecido"),
    )
    
    data = models.DateTimeField(
        verbose_name=_("Data e Hora"),
        default=timezone.now,
        help_text=_("Data e hora do abastecimento"),
    )
    
    km_atual = models.PositiveIntegerField(
        verbose_name=_("Quilometragem Atual"),
        validators=[MinValueValidator(1)],
        help_text=_("Quilometragem do veículo no momento do abastecimento"),
    )
    
    litros = models.DecimalField(
        verbose_name=_("Litros"),
        max_digits=7,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text=_("Quantidade de combustível abastecida em litros"),
    )
    
    valor_total = models.DecimalField(
        verbose_name=_("Valor Total"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Valor total pago pelo combustível"),
    )
    
    posto = models.CharField(
        verbose_name=_("Posto de Combustível"),
        max_length=100,
        blank=True,
        help_text=_("Nome do posto onde foi realizado o abastecimento"),
    )
    
    observacao = models.TextField(
        verbose_name=_("Observação"),
        blank=True,
        help_text=_("Observações sobre o abastecimento"),
    )

    # Manager
    objects = AbastecimentoManager()

    class Meta:
        verbose_name = _("Abastecimento")
        verbose_name_plural = _("Abastecimentos")
        ordering = ['-data']
        indexes = [
            models.Index(fields=['veiculo', '-data']),
            models.Index(fields=['-data']),
            models.Index(fields=['km_atual']),
        ]

    
    # STRING REPRESENTATION
    
    
    def __str__(self) -> str:
        return f"Abastecimento {self.veiculo.placa} - {self.data.strftime('%d/%m/%Y %H:%M')}"

    
    # PROPERTIES
    
    
    @property
    def valor_por_litro(self):
        """Calcula o valor por litro do combustível."""
        if self.litros > 0:
            return self.valor_total / self.litros
        return Decimal('0.00')
    
    @property
    def data_formatada(self):
        """Retorna a data formatada."""
        return self.data.strftime('%d/%m/%Y %H:%M')
    
    @property
    def km_percorridos_desde_ultimo(self):
        """Calcula KM percorridos desde o último abastecimento."""
        ultimo_abastecimento = self.veiculo.abastecimentos.filter(
            data__lt=self.data
        ).first()
        
        if ultimo_abastecimento:
            return self.km_atual - ultimo_abastecimento.km_atual
        return None
    
    @property
    def consumo_medio(self):
        """Calcula o consumo médio desde o último abastecimento."""
        km_percorridos = self.km_percorridos_desde_ultimo
        if km_percorridos and self.litros > 0:
            return Decimal(km_percorridos) / self.litros
        return None

    
    # CUSTOM SAVE METHOD
    
    
    def save(self, *args, **kwargs):
        """Processa dados antes de salvar."""
        # Normaliza campos de texto
        if self.observacao:
            self.observacao = self.observacao.upper().strip()
        
        if self.posto:
            self.posto = self.posto.upper().strip()
        
        # Atualiza quilometragem do veículo
        if self.km_atual > self.veiculo.km_atual:
            self.veiculo.km_atual = self.km_atual
            self.veiculo.save(update_fields=['km_atual'])
        
        super().save(*args, **kwargs)

    
    # VALIDATION METHODS
    
    
    def clean(self):
        """Validações personalizadas do modelo."""
        super().clean()
        
        self._validate_quilometragem()
        self._validate_data_futura()
        self._validate_veiculo_condicao()
    
    def _validate_quilometragem(self):
        """Valida se a quilometragem é consistente."""
        if self.veiculo and self.km_atual < self.veiculo.km_atual:
            raise ValidationError({
                'km_atual': _(
                    f"Quilometragem não pode ser menor que a atual "
                    f"do veículo ({self.veiculo.km_atual} km)."
                )
            })
        
        # Verifica se não há abastecimento posterior com KM menor
        if self.pk and self.veiculo:
            abastecimentos_posteriores = self.veiculo.abastecimentos.filter(
                data__gt=self.data,
                km_atual__lt=self.km_atual
            )
            if abastecimentos_posteriores.exists():
                raise ValidationError({
                    'km_atual': _(
                        "Existe abastecimento posterior com "
                        "quilometragem menor."
                    )
                })
    
    def _validate_data_futura(self):
        """Valida se a data não é futura."""
        if self.data > timezone.now():
            raise ValidationError({
                'data': _("Data do abastecimento não pode ser futura.")
            })
    
    def _validate_veiculo_condicao(self):
        """Valida se o veículo está em condições para abastecimento."""
        if self.veiculo and not self.veiculo.em_condicao:
            raise ValidationError({
                'veiculo': _(
                    "Não é possível registrar abastecimento para "
                    "veículo que não está em condições de uso."
                )
            })

    
    # BUSINESS METHODS
    
    
    def calcular_economia(self, preco_referencia):
        """
        Calcula economia ou gasto extra baseado em preço de referência.
        
        Args:
            preco_referencia (Decimal): Preço por litro de referência
            
        Returns:
            Decimal: Valor economizado (positivo) ou gasto extra (negativo)
        """
        diferenca_preco = preco_referencia - self.valor_por_litro
        return diferenca_preco * self.litros
    
    def get_proximo_abastecimento(self):
        """Retorna o próximo abastecimento cronológico."""
        return self.veiculo.abastecimentos.filter(
            data__gt=self.data
        ).last()
    
    def get_abastecimento_anterior(self):
        """Retorna o abastecimento anterior cronológico."""
        return self.veiculo.abastecimentos.filter(
            data__lt=self.data
        ).first()
