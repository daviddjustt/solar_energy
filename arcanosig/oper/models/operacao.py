# Django Core
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Local Apps
from arcanosig.oper.models.base import BaseModel
from arcanosig.users.models import User
from arcanosig.oper.models.veiculo import Veiculo

# MAIN MODELS


class Operacao(BaseModel):
    """
    Modelo para operações policiais.
    
    Representa operações policiais com controle de datas, status e validações
    para garantir consistência temporal e organizacional.
    """
    

    # FIELDS

    
    name = models.CharField(
        verbose_name=_("Nome"),
        max_length=255,
        help_text=_("Nome identificador da operação policial"),
    )
    
    description = models.TextField(
        verbose_name=_("Descrição"),
        blank=True,
        help_text=_("Descrição detalhada dos objetivos e características da operação"),
    )
    
    start_date = models.DateField(
        verbose_name=_("Data de Início"),
        help_text=_("Data de início da operação"),
    )
    
    end_date = models.DateField(
        verbose_name=_("Data de Término"),
        help_text=_("Data prevista para término da operação"),
    )
    
    is_active = models.BooleanField(
        verbose_name=_("Ativa"),
        default=True,
        help_text=_("Indica se a operação está atualmente ativa"),
    )

    class Meta:
        ordering = ["-start_date"]
        verbose_name = _("Operação")
        verbose_name_plural = _("Operações")
        indexes = [
            models.Index(fields=["-start_date"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["name"]),
        ]
        unique_together = ["name", "start_date"]


    # STRING REPRESENTATION

    
    def __str__(self) -> str:
        return f"{self.name} ({self.start_date} - {self.end_date})"


    # PROPERTIES

    
    @property
    def duracao_dias(self):
        """Calcula a duração da operação em dias."""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0
    
    @property
    def status_display(self):
        """Retorna o status atual da operação."""
        hoje = timezone.now().date()
        
        if not self.is_active:
            return _("Inativa")
        elif hoje < self.start_date:
            return _("Agendada")
        elif hoje > self.end_date:
            return _("Expirada")
        else:
            return _("Em Andamento")
    
    @property
    def dias_restantes(self):
        """Calcula quantos dias restam para o fim da operação."""
        hoje = timezone.now().date()
        if self.end_date and hoje <= self.end_date:
            return (self.end_date - hoje).days
        return 0


    # CUSTOM SAVE METHOD

    
    def save(self, *args, **kwargs) -> None:
        """Processa dados antes de salvar."""
        self._normalize_fields()
        self.clean()
        super().save(*args, **kwargs)
    
    def _normalize_fields(self):
        """Normaliza campos de texto para maiúsculas."""
        if self.name:
            self.name = self.name.upper().strip()
        if self.description:
            self.description = self.description.upper().strip()


    # VALIDATION METHODS

    
    def clean(self):
        """Validações centralizadas para a operação."""
        super().clean()
        
        if not self.start_date or not self.end_date:
            return  # Deixa o Django lidar com campos obrigatórios vazios
        
        self._validate_date_logic()
        self._validate_past_dates()
        self._validate_future_dates()
    
    def _validate_date_logic(self):
        """Valida a lógica das datas."""
        if self.start_date > self.end_date:
            raise ValidationError(
                _("A data de início não pode ser posterior à data de término.")
            )
    
    def _validate_past_dates(self):
        """Valida restrições de datas no passado."""
        hoje = timezone.now().date()
        
        # Nova operação com data no passado
        if not self.pk and self.start_date < hoje:
            raise ValidationError(
                _("Não é possível criar uma operação com data de início no passado.")
            )
        
        # Operação existente com alteração para o passado
        if self.pk and self.is_active:
            try:
                original = Operacao.objects.get(pk=self.pk)
                if (self.start_date != original.start_date and 
                    self.start_date < hoje):
                    raise ValidationError(
                        _("Não é possível alterar a data de início para uma data no passado.")
                    )
            except Operacao.DoesNotExist:
                pass
    
    def _validate_future_dates(self):
        """Valida datas muito distantes no futuro."""
        limite_futuro = timezone.now().date().replace(
            year=timezone.now().date().year + 5
        )
        
        if (self.start_date > limite_futuro or 
            self.end_date > limite_futuro):
            raise ValidationError(
                _("As datas não podem estar mais de 5 anos no futuro.")
            )


    # BUSINESS METHODS

    
    def check_and_update_status(self):
        """
        Verifica e atualiza o status da operação baseado na data final.
        
        Returns:
            bool: True se o status foi alterado
        """
        if self.end_date and self.end_date < timezone.now().date() and self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active'])
            return True
        return False
    
    def ativar(self):
        """Ativa a operação se as condições permitirem."""
        hoje = timezone.now().date()
        
        if self.end_date < hoje:
            raise ValidationError(
                _("Não é possível ativar uma operação com data de término no passado.")
            )
        
        self.is_active = True
        self.save(update_fields=['is_active'])
    
    def desativar(self):
        """Desativa a operação."""
        self.is_active = False
        self.save(update_fields=['is_active'])


class Guarnicao(BaseModel):
    """
    Modelo para as guarnições (equipes) que participam das operações.
    
    Representa uma equipe policial com comandante, membros e veículo
    associado a uma operação específica.
    """
    

    # FIELDS

    
    name = models.CharField(
        verbose_name=_("Nome da Guarnição"),
        max_length=50,
        help_text=_("Nome identificador da guarnição"),
    )
    
    operacao = models.ForeignKey(
        Operacao,
        verbose_name=_("Operação"),
        on_delete=models.CASCADE,
        related_name="guarnicoes",
        help_text=_("Operação à qual esta guarnição pertence"),
    )
    
    comandante = models.ForeignKey(
        User,
        verbose_name=_("Comandante"),
        on_delete=models.PROTECT,
        related_name="guarnicoes_as_comandante",
        limit_choices_to={'is_active': True, 'is_operacoes': True},
        help_text=_("Policial responsável pelo comando da guarnição"),
    )
    
    membros = models.ManyToManyField(
        User,
        through="GuarnicaoMembro",
        verbose_name=_("Membros"),
        related_name="guarnicoes_as_membro",
        limit_choices_to={'is_active': True, 'is_operacoes': True},
        help_text=_("Policiais que compõem a guarnição"),
    )
    
    veiculo = models.OneToOneField(
        Veiculo,
        verbose_name=_("Veículo"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guarnicao_associada",
        help_text=_("Veículo designado para esta guarnição"),
    )

    class Meta:
        verbose_name = _("Guarnição")
        verbose_name_plural = _("Guarnições")
        ordering = ['name']
        indexes = [
            models.Index(fields=['operacao', 'name']),
            models.Index(fields=['comandante']),
        ]


    # STRING REPRESENTATION

    
    def __str__(self):
        return f"{self.name} - {self.operacao.name}"


    # PROPERTIES

    
    @property
    def total_membros(self):
        """Retorna o número total de membros da guarnição."""
        return self.guarnicao_membros.count()
    
    @property
    def membros_ativos(self):
        """Retorna queryset com membros ativos da guarnição."""
        return self.membros.filter(is_active=True)
    
    @property
    def tem_veiculo(self):
        """Verifica se a guarnição tem veículo associado."""
        return self.veiculo is not None


    # CUSTOM SAVE METHOD

    
    def save(self, *args, **kwargs) -> None:
        """Processa dados antes de salvar."""
        if self.name:
            self.name = self.name.upper().strip()
        
        self.clean()
        super().save(*args, **kwargs)
        
        # Garante que o comandante seja um membro
        self._ensure_comandante_is_member()
    
    def _ensure_comandante_is_member(self):
        """Garante que o comandante seja automaticamente um membro."""
        if self.comandante:
            GuarnicaoMembro.objects.get_or_create(
                guarnicao=self,
                user=self.comandante
            )


    # VALIDATION METHODS

    
    def clean(self):
        """Validações centralizadas para a guarnição."""
        super().clean()
        
        if not self.operacao:
            return  # Deixa o Django lidar com campos obrigatórios vazios
        
        self._validate_operacao_ativa()
        self._validate_comandante()
    
    def _validate_operacao_ativa(self):
        """Valida se a operação está ativa."""
        if not self.operacao.is_active:
            raise ValidationError(
                _("Não é possível criar ou editar guarnições em operações inativas.")
            )
    
    def _validate_comandante(self):
        """Valida se o comandante está apto."""
        if not self.comandante:
            return
        
        if not self.comandante.is_active:
            raise ValidationError(
                _("O comandante deve ser um usuário ativo.")
            )


    # BUSINESS METHODS

    
    def adicionar_membro(self, user):
        """
        Adiciona um membro à guarnição.
        
        Args:
            user: Usuário a ser adicionado
        
        Returns:
            GuarnicaoMembro: Instância criada ou existente
        """
        membro, created = GuarnicaoMembro.objects.get_or_create(
            guarnicao=self,
            user=user
        )
        return membro
    
    def remover_membro(self, user):
        """
        Remove um membro da guarnição.
        
        Args:
            user: Usuário a ser removido
        
        Returns:
            bool: True se removido com sucesso
        """
        if user == self.comandante:
            raise ValidationError(
                _("Não é possível remover o comandante da guarnição.")
            )
        
        try:
            membro = GuarnicaoMembro.objects.get(guarnicao=self, user=user)
            membro.delete()
            return True
        except GuarnicaoMembro.DoesNotExist:
            return False


class GuarnicaoMembro(BaseModel):
    """
    Modelo que representa a associação entre um usuário e uma guarnição.
    
    Tabela intermediária que controla os membros de cada guarnição,
    com validações para garantir consistência.
    """
    

    # FIELDS

    
    guarnicao = models.ForeignKey(
        Guarnicao,
        on_delete=models.CASCADE,
        related_name="guarnicao_membros",
        verbose_name=_("Guarnição"),
        help_text=_("Guarnição à qual o usuário pertence"),
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="guarnicao_membros",
        verbose_name=_("Usuário"),
        limit_choices_to={'is_active': True},
        help_text=_("Policial membro da guarnição"),
    )

    class Meta:
        verbose_name = _("Membro de Guarnição")
        verbose_name_plural = _("Membros de Guarnições")
        unique_together = ['guarnicao', 'user']
        indexes = [
            models.Index(fields=['guarnicao', 'user']),
            models.Index(fields=['user']),
        ]


    # STRING REPRESENTATION

    
    def __str__(self) -> str:
        return f"{self.user.name} - {self.guarnicao.name}"


    # PROPERTIES

    
    @property
    def is_comandante(self):
        """Verifica se este membro é o comandante da guarnição."""
        return self.user == self.guarnicao.comandante
    
    @property
    def operacao(self):
        """Retorna a operação da guarnição."""
        return self.guarnicao.operacao


    # VALIDATION METHODS

    
    def clean(self):
        """Validações centralizadas para o membro da guarnição."""
        super().clean()
        
        if not self.guarnicao:
            return  # Deixa o Django lidar com campos obrigatórios vazios
        
        self._validate_operacao_ativa()
        self._validate_user_ativo()
        self._validate_membro_unico_por_operacao()
    
    def _validate_operacao_ativa(self):
        """Valida se a operação está ativa."""
        if not self.guarnicao.operacao.is_active:
            raise ValidationError(
                _("Não é possível adicionar membros em guarnições de operações inativas.")
            )
    
    def _validate_user_ativo(self):
        """Valida se o usuário está ativo."""
        if not self.user.is_active:
            raise ValidationError(
                _("Apenas usuários ativos podem ser membros de guarnições.")
            )
    
    def _validate_membro_unico_por_operacao(self):
        """Valida se o usuário não está em outra guarnição da mesma operação."""
        if not self.guarnicao.pk:
            return  # Aguarda a guarnição ser salva
        
        outras_guarnicoes = GuarnicaoMembro.objects.filter(
            user=self.user,
            guarnicao__operacao=self.guarnicao.operacao
        ).exclude(guarnicao=self.guarnicao)
        
        if outras_guarnicoes.exists() and not self.pk:
            raise ValidationError(
                _("O usuário já é membro de outra guarnição nesta operação.")
            )
