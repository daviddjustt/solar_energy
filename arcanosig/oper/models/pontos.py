from datetime import datetime
from typing import Optional, List
from decimal import Decimal

# Django Core
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator, 
    MinValueValidator, 
    RegexValidator
)
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django_fsm import FSMField, transition

from arcanosig.oper.models.base import BaseModel


# ENUMS AND CHOICES


class PontosEstados(models.TextChoices):
    """Estados possíveis de um ponto de fiscalização."""
    REGISTRADA = "REGISTRADA", _("Registrada")
    FASE_INTELIGENCIA = "FASE_INTELIGENCIA", _("Fase de Inteligência")
    EM_FISCALIZACAO = "EM_FISCALIZACAO", _("Em Fiscalização")
    ARQUIVADA = "ARQUIVADA", _("Arquivada")


class PontosAcoes(models.TextChoices):
    """Ações possíveis em um ponto de fiscalização."""
    VALIDAR = "VALIDAR", _("Validar")
    ARQUIVAR = "ARQUIVAR", _("Arquivar")


class OrgaoFonte(models.IntegerChoices):
    """Órgãos fontes disponíveis com IDs."""
    IBAMA = 1, _("IBAMA")
    POLICIA_AMBIENTAL = 2, _("Polícia Ambiental")
    POLICIA_FEDERAL = 3, _("Polícia Federal")
    POLICIA_CIVIL = 4, _("Polícia Civil")
    MINISTERIO_PUBLICO = 5, _("Ministério Público")
    RECEITA_FEDERAL = 6, _("Receita Federal")
    PREFEITURA = 7, _("Prefeitura")
    OUTROS = 8, _("Outros")



# MIXINS AND ABSTRACT MODELS


class ArquivoMixin(models.Model):
    """
    Mixin para campos comuns de arquivos.
    
    Fornece estrutura base para modelos que lidam com upload de arquivos,
    incluindo campos comuns e métodos de validação.
    """
    
    arquivo = models.FileField(
        verbose_name=_("Arquivo"),
        upload_to="pontos/%(class)s/",
        help_text=_("Arquivo relacionado ao ponto de fiscalização"),
    )
    
    descricao = models.CharField(
        verbose_name=_("Descrição"),
        max_length=255,
        help_text=_("Descrição do conteúdo do arquivo"),
    )

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.descricao



# AUXILIARY MODELS


class Municipio(models.Model):
    """
    Modelo para municípios brasileiros.
    
    Representa os municípios do Brasil com seus respectivos estados,
    utilizando códigos IBGE como chave primária.
    """
    

    # FIELDS

    
    id = models.IntegerField(
        verbose_name=_("ID IBGE"),
        primary_key=True,
        help_text=_("Código IBGE do município"),
    )
    
    name = models.CharField(
        verbose_name=_("Nome"),
        max_length=100,
        help_text=_("Nome oficial do município"),
    )
    
    state = models.CharField(
        verbose_name=_("Estado"),
        max_length=2,
        help_text=_("Sigla do estado (UF)"),
    )

    class Meta:
        ordering = ["name"]
        verbose_name = _("Município")
        verbose_name_plural = _("Municípios")
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['state']),
        ]


    # STRING REPRESENTATION

    
    def __str__(self) -> str:
        return f"{self.name} - {self.state}"


    # PROPERTIES

    
    @property
    def nome_completo(self):
        """Retorna nome completo com estado."""
        return f"{self.name}/{self.state}"


class PontosFoto(ArquivoMixin, BaseModel):
    """
    Modelo para fotos de pontos de fiscalização.
    
    Armazena imagens relacionadas aos pontos com validações
    específicas para formatos e quantidade.
    """
    

    # FIELDS

    
    arquivo = models.ImageField(
        verbose_name=_("Foto"),
        upload_to="pontos/fotos/%Y/%m/",
        help_text=_("Formatos permitidos: jpg, jpeg, png, webp"),
    )

    class Meta:
        verbose_name = _("Foto do Ponto")
        verbose_name_plural = _("Fotos dos Pontos")
        ordering = ['-created_at']


    # VALIDATION METHODS

    
    def clean(self) -> None:
        """Valida o número máximo de fotos por ponto."""
        super().clean()
        
        if hasattr(self, 'pontos'):
            fotos_count = self.pontos.fotos.count()
            if fotos_count >= 10 and not self.pk:
                raise ValidationError(
                    _("Máximo de 10 fotos por ponto de fiscalização.")
                )


    # PROPERTIES

    
    @property
    def tamanho_formatado(self):
        """Retorna o tamanho do arquivo formatado."""
        if self.arquivo:
            tamanho = self.arquivo.size
            if tamanho < 1024:
                return f"{tamanho} B"
            elif tamanho < 1024 * 1024:
                return f"{tamanho / 1024:.1f} KB"
            else:
                return f"{tamanho / (1024 * 1024):.1f} MB"
        return "0 B"


class PontosDocumento(ArquivoMixin, BaseModel):
    """
    Modelo para documentos de pontos de fiscalização.
    
    Armazena documentos PDF relacionados aos pontos com validações
    específicas para formato e quantidade.
    """
    

    # FIELDS

    
    arquivo = models.FileField(
        verbose_name=_("Documento"),
        upload_to="pontos/documentos/%Y/%m/",
        validators=[FileExtensionValidator(["pdf"])],
        help_text=_("Apenas arquivos PDF são permitidos"),
    )

    class Meta:
        verbose_name = _("Documento do Ponto")
        verbose_name_plural = _("Documentos dos Pontos")
        ordering = ['-created_at']


    # VALIDATION METHODS

    
    def clean(self) -> None:
        """Valida o número máximo de documentos por ponto."""
        super().clean()
        
        if hasattr(self, 'pontos'):
            docs_count = self.pontos.documentos.count()
            if docs_count >= 3 and not self.pk:
                raise ValidationError(
                    _("Máximo de 3 documentos por ponto de fiscalização.")
                )


    # PROPERTIES

    
    @property
    def tamanho_formatado(self):
        """Retorna o tamanho do arquivo formatado."""
        if self.arquivo:
            tamanho = self.arquivo.size
            if tamanho < 1024 * 1024:
                return f"{tamanho / 1024:.1f} KB"
            else:
                return f"{tamanho / (1024 * 1024):.1f} MB"
        return "0 B"


class PontosLog(BaseModel):
    """
    Modelo para log de alterações de estado do ponto.
    
    Registra todas as mudanças de estado dos pontos para auditoria
    e acompanhamento do fluxo de trabalho.
    """
    

    # FIELDS

    
    pontos = models.ForeignKey(
        'Pontos',
        verbose_name=_("Ponto"),
        on_delete=models.CASCADE,
        related_name='logs',
        help_text=_("Ponto de fiscalização relacionado"),
    )
    
    estado_anterior = models.CharField(
        verbose_name=_("Estado Anterior"),
        max_length=50,
        choices=PontosEstados.choices,
        help_text=_("Estado antes da mudança"),
    )
    
    novo_estado = models.CharField(
        verbose_name=_("Novo Estado"),
        max_length=50,
        choices=PontosEstados.choices,
        help_text=_("Estado após a mudança"),
    )
    
    observacao = models.TextField(
        verbose_name=_("Observação"),
        blank=True,
        help_text=_("Observações sobre a mudança de estado"),
    )
    
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Usuário"),
        on_delete=models.PROTECT,
        related_name='pontos_logs',
        help_text=_("Usuário responsável pela mudança"),
    )

    class Meta:
        verbose_name = _("Log de Ponto")
        verbose_name_plural = _("Logs de Pontos")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=['pontos', '-created_at']),
            models.Index(fields=['novo_estado']),
            models.Index(fields=['usuario']),
        ]


    # STRING REPRESENTATION

    
    def __str__(self) -> str:
        return f"{self.pontos.protocolo}: {self.estado_anterior} → {self.novo_estado}"


    # PROPERTIES

    
    @property
    def duracao_estado_anterior(self):
        """Calcula quanto tempo ficou no estado anterior."""
        if hasattr(self, '_duracao'):
            return self._duracao
        return None



# MANAGERS


class PontosManager(models.Manager):
    """Manager customizado para pontos de fiscalização."""
    
    PROTOCOL_PREFIX = "PM"

    def gerar_protocolo(self) -> str:
        """
        Gera um novo número de protocolo no formato {prefixo}{ano}{sequencia}.
        
        Returns:
            str: Protocolo único no formato PM202400001
        """
        ano_atual = datetime.now().year
        ultima_pontos = self.filter(
            protocolo__startswith=f"{self.PROTOCOL_PREFIX}{ano_atual}"
        ).order_by('-protocolo').first()
        
        if ultima_pontos:
            # Extrai a parte numérica do protocolo
            ultimo_numero = int(ultima_pontos.protocolo[len(self.PROTOCOL_PREFIX) + 4:])
            novo_numero = str(ultimo_numero + 1).zfill(5)
        else:
            novo_numero = "00001"
        
        return f"{self.PROTOCOL_PREFIX}{ano_atual}{novo_numero}"
    
    def ativos(self):
        """Retorna pontos que não estão arquivados."""
        return self.exclude(estado_atual=PontosEstados.ARQUIVADA)
    
    def em_andamento(self):
        """Retorna pontos em fase de inteligência ou fiscalização."""
        return self.filter(
            estado_atual__in=[
                PontosEstados.FASE_INTELIGENCIA,
                PontosEstados.EM_FISCALIZACAO
            ]
        )
    
    def por_estado(self, estado):
        """Retorna pontos filtrados por estado."""
        return self.filter(estado_atual=estado)



# MAIN MODEL


class Pontos(BaseModel):
    """
    Modelo principal para gestão de pontos de fiscalização.
    
    Implementa FSM (Finite State Machine) para controle rigoroso de estados
    e validações de negócio específicas para operações policiais.
    """
    

    # FIELDS

    
    # Relacionamentos principais
    operacao = models.ForeignKey(
        "oper.Operacao",
        verbose_name=_("Operação"),
        on_delete=models.PROTECT,
        related_name="pontos",
        help_text=_("Operação policial relacionada"),
    )
    
    protocolo = models.CharField(
        verbose_name=_("Protocolo"),
        max_length=20,
        unique=True,
        editable=False,
        help_text=_("Número de protocolo único gerado automaticamente"),
    )
    
    guarnicao = models.ManyToManyField(
        "oper.Guarnicao",
        verbose_name=_("Guarnições"),
        related_name="pontos",
        blank=True,
        help_text=_("Guarnições responsáveis pelo ponto"),
    )
    
    # Campos de localização
    endereco = models.CharField(
        verbose_name=_("Endereço"),
        max_length=255,
        help_text=_("Endereço completo do local"),
    )
    
    cep = models.CharField(
        verbose_name=_("CEP"),
        max_length=8,
        validators=[
            RegexValidator(
                regex=r'^\d{8}$',
                message=_('CEP deve conter 8 dígitos numéricos')
            )
        ],
        help_text=_("CEP no formato 12345678"),
    )
    
    latitude = models.DecimalField(
        verbose_name=_("Latitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text=_("Coordenada de latitude em decimal"),
    )
    
    longitude = models.DecimalField(
        verbose_name=_("Longitude"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text=_("Coordenada de longitude em decimal"),
    )
    
    municipio = models.ForeignKey(
        Municipio,
        verbose_name=_("Município"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_("Município onde está localizado o ponto"),
    )
    
    estado = models.CharField(
        verbose_name=_("Estado"),
        max_length=2,
        editable=False,
        help_text=_("Estado obtido automaticamente do município"),
    )
    
    # Relacionamentos com arquivos
    fotos = models.ManyToManyField(
        PontosFoto,
        verbose_name=_("Fotos"),
        related_name="pontos",
        blank=True,
        help_text=_("Fotos do local (máximo 10)"),
    )
    
    documentos = models.ManyToManyField(
        PontosDocumento,
        verbose_name=_("Documentos"),
        related_name="pontos",
        blank=True,
        help_text=_("Documentos relacionados (máximo 3 PDFs)"),
    )
    
    # Campos adicionais
    observacoes = models.TextField(
        verbose_name=_("Observações"),
        blank=True,
        help_text=_("Observações gerais sobre o ponto"),
    )
    
    # Estado FSM
    estado_atual = FSMField(
        verbose_name=_("Estado Atual"),
        default=PontosEstados.REGISTRADA,
        choices=PontosEstados.choices,
        protected=True,
        help_text=_("Estado atual do ponto no fluxo de trabalho"),
    )
    
    # Campos de TCO
    tco = models.BooleanField(
        verbose_name=_("Foi confeccionado TCO?"),
        default=False,
        help_text=_("Indica se foi elaborado Termo Circunstanciado de Ocorrência"),
    )
    
    tco_numero = models.CharField(
        verbose_name=_("Número do TCO"),
        max_length=20,
        null=True,
        blank=True,
        help_text=_("Número do TCO se foi confeccionado"),
    )
    
    # Campos de controle de datas das fases
    data_inicio_fase_inteligencia = models.DateTimeField(
        verbose_name=_("Início da Fase de Inteligência"),
        null=True,
        blank=True,
        help_text=_("Data e hora de início da fase de inteligência"),
    )
    
    data_fim_fase_inteligencia = models.DateTimeField(
        verbose_name=_("Fim da Fase de Inteligência"),
        null=True,
        blank=True,
        help_text=_("Data e hora de fim da fase de inteligência"),
    )
    
    data_inicio_fiscalizacao = models.DateTimeField(
        verbose_name=_("Início da Fiscalização"),
        null=True,
        blank=True,
        help_text=_("Data e hora de início da fiscalização"),
    )
    
    data_fim_fiscalizacao = models.DateTimeField(
        verbose_name=_("Fim da Fiscalização"),
        null=True,
        blank=True,
        help_text=_("Data e hora de fim da fiscalização"),
    )

    # Manager
    objects = PontosManager()

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("pode_mudar_estado", _("Pode mudar o estado dos pontos")),
            ("pode_visualizar_equipe", _("Pode visualizar os pontos da equipe")),
        ]
        verbose_name = _("Ponto")
        verbose_name_plural = _("Pontos")
        indexes = [
            models.Index(fields=['protocolo']),
            models.Index(fields=['estado_atual']),
            models.Index(fields=['created_at']),
            models.Index(fields=['operacao', 'estado_atual']),
            models.Index(fields=['municipio']),
            models.Index(fields=['data_inicio_fase_inteligencia']),
            models.Index(fields=['data_inicio_fiscalizacao']),
        ]


    # STRING REPRESENTATION

    
    def __str__(self) -> str:
        return f"{self.protocolo} - {self.get_estado_atual_display()}"


    # PROPERTIES

    
    @property
    def localizacao_completa(self):
        """Retorna a localização completa formatada."""
        partes = [self.endereco]
        if self.municipio:
            partes.append(f"{self.municipio.name}/{self.estado}")
        if self.cep:
            partes.append(f"CEP: {self.cep}")
        return " - ".join(partes)
    
    @property
    def tem_coordenadas(self):
        """Verifica se possui coordenadas geográficas."""
        return self.latitude is not None and self.longitude is not None
    
    @property
    def total_fotos(self):
        """Retorna o número total de fotos."""
        return self.fotos.count()
    
    @property
    def total_documentos(self):
        """Retorna o número total de documentos."""
        return self.documentos.count()
    
    @property
    def duracao_fase_inteligencia(self):
        """Calcula a duração da fase de inteligência."""
        if (self.data_inicio_fase_inteligencia and 
            self.data_fim_fase_inteligencia):
            return (self.data_fim_fase_inteligencia - 
                   self.data_inicio_fase_inteligencia)
        return None
    
    @property
    def duracao_fiscalizacao(self):
        """Calcula a duração da fiscalização."""
        if (self.data_inicio_fiscalizacao and 
            self.data_fim_fiscalizacao):
            return (self.data_fim_fiscalizacao - 
                   self.data_inicio_fiscalizacao)
        return None
    
    @property
    def duracao_total(self):
        """Calcula a duração total do processo."""
        if (self.data_inicio_fase_inteligencia and 
            self.data_fim_fiscalizacao):
            return (self.data_fim_fiscalizacao - 
                   self.data_inicio_fase_inteligencia)
        return None


    # CUSTOM SAVE METHOD

    
    def save(self, *args, **kwargs) -> None:
        """Processa dados antes de salvar."""
        novo_registro = not self.pk
        
        # Gera protocolo se necessário
        if novo_registro and not self.protocolo:
            self.protocolo = Pontos.objects.gerar_protocolo()
        
        # Atualiza o estado baseado no município
        if self.municipio and self.municipio.state != self.estado:
            self.estado = self.municipio.state
        
        # Normaliza campos de texto
        self._normalize_fields()
        
        super().save(*args, **kwargs)
        
        # Atualiza operação baseada na guarnição se necessário
        self._update_operacao_from_guarnicao()
    
    def _normalize_fields(self):
        """Normaliza campos de texto."""
        if self.endereco:
            self.endereco = self.endereco.upper().strip()
        if self.observacoes:
            self.observacoes = self.observacoes.strip()
        if self.tco_numero:
            self.tco_numero = self.tco_numero.upper().strip()
    
    def _update_operacao_from_guarnicao(self):
        """Atualiza operação baseada na primeira guarnição se não definida."""
        if self.guarnicao.exists() and not self.operacao:
            primeira_guarnicao = self.guarnicao.first()
            if primeira_guarnicao and primeira_guarnicao.operacao:
                self.operacao = primeira_guarnicao.operacao
                self.save(update_fields=['operacao'])


    # VALIDATION METHODS

    
    def clean(self) -> None:
        """Validações personalizadas do modelo."""
        super().clean()
        
        self._validate_fase_inteligencia_dates()
        self._validate_fiscalizacao_dates()
        self._validate_fases_sequence()
        self._validate_tco_fields()
    
    def _validate_fase_inteligencia_dates(self):
        """Valida datas da fase de inteligência."""
        if (self.data_fim_fase_inteligencia and 
            not self.data_inicio_fase_inteligencia):
            raise ValidationError({
                'data_fim_fase_inteligencia': _(
                    "Não é possível definir data fim sem data início."
                )
            })
        
        if (self.data_inicio_fase_inteligencia and 
            self.data_fim_fase_inteligencia):
            if self.data_fim_fase_inteligencia < self.data_inicio_fase_inteligencia:
                raise ValidationError({
                    'data_fim_fase_inteligencia': _(
                        "Data fim não pode ser anterior à data início."
                    )
                })
    
    def _validate_fiscalizacao_dates(self):
        """Valida datas da fiscalização."""
        if (self.data_fim_fiscalizacao and 
            not self.data_inicio_fiscalizacao):
            raise ValidationError({
                'data_fim_fiscalizacao': _(
                    "Não é possível definir data fim sem data início."
                )
            })
        
        if (self.data_inicio_fiscalizacao and 
            self.data_fim_fiscalizacao):
            if self.data_fim_fiscalizacao < self.data_inicio_fiscalizacao:
                raise ValidationError({
                    'data_fim_fiscalizacao': _(
                        "Data fim não pode ser anterior à data início."
                    )
                })
    
    def _validate_fases_sequence(self):
        """Valida sequência entre as fases."""
        if (self.data_inicio_fiscalizacao and 
            self.data_fim_fase_inteligencia):
            if self.data_inicio_fiscalizacao < self.data_fim_fase_inteligencia:
                raise ValidationError({
                    'data_inicio_fiscalizacao': _(
                        "Fiscalização não pode iniciar antes do fim da fase de inteligência."
                    )
                })
    
    def _validate_tco_fields(self):
        """Valida campos relacionados ao TCO."""
        if self.tco_numero and not self.tco:
            raise ValidationError({
                'tco_numero': _(
                    "Número do TCO só pode ser preenchido se TCO foi confeccionado."
                )
            })


    # PERMISSION METHODS

    
    def pode_mudar_estado(self, user: settings.AUTH_USER_MODEL) -> bool:
        """
        Verifica se o usuário tem permissão para mudar o estado.
        
        Args:
            user: Usuário que está tentando fazer a mudança
        
        Returns:
            bool: True se pode mudar o estado
        """
        # Verifica permissão específica
        if not user.has_perm('oper.pode_mudar_estado'):
            return False
        
        # Estados que permitem mudança
        estados_mudaveis = [
            PontosEstados.REGISTRADA,
            PontosEstados.FASE_INTELIGENCIA,
            PontosEstados.EM_FISCALIZACAO
        ]
        
        return self.estado_atual in estados_mudaveis
    
    def pode_editar(self, user: settings.AUTH_USER_MODEL) -> bool:
        """Verifica se o usuário pode editar o ponto."""
        # Não pode editar se arquivado
        if self.estado_atual == PontosEstados.ARQUIVADA:
            return False
        
        # Verifica se é membro de alguma guarnição relacionada
        if self.guarnicao.filter(
            guarnicao_membros__user=user
        ).exists():
            return True
        
        # Verifica permissões específicas
        return user.has_perm('oper.change_pontos')


    # FSM TRANSITIONS

    
    @transition(
        field=estado_atual,
        source=PontosEstados.REGISTRADA,
        target=PontosEstados.FASE_INTELIGENCIA,
        permission=lambda instance, user: instance.pode_mudar_estado(user),
        custom={
            'nome': _("Iniciar Fase de Inteligência"),
            'descricao': _("Inicia o processo de fase de inteligência"),
        }
    )
    def iniciar_fase_inteligencia(self, user: settings.AUTH_USER_MODEL) -> None:
        """Inicia o processo de fase de inteligência."""
        from django.utils import timezone
        
        self.data_inicio_fase_inteligencia = timezone.now()
        self._create_log(
            PontosEstados.REGISTRADA,
            PontosEstados.FASE_INTELIGENCIA,
            user,
            "Iniciada fase de inteligência"
        )
    
    @transition(
        field=estado_atual,
        source=PontosEstados.FASE_INTELIGENCIA,
        target=PontosEstados.EM_FISCALIZACAO,
        permission=lambda instance, user: instance.pode_mudar_estado(user),
        custom={
            'nome': _("Validar Ponto"),
            'descricao': _("Valida o ponto e move para fiscalização"),
        }
    )
    def validar_ponto(self, user: settings.AUTH_USER_MODEL) -> str:
        """Valida o ponto e move para fiscalização."""
        from django.utils import timezone
        
        if not self.guarnicao.exists():
            raise ValidationError(
                _("Ponto precisa ter uma guarnição atribuída.")
            )
        
        self.data_fim_fase_inteligencia = timezone.now()
        self.data_inicio_fiscalizacao = timezone.now()
        
        self._create_log(
            PontosEstados.FASE_INTELIGENCIA,
            PontosEstados.EM_FISCALIZACAO,
            user,
            "Ponto validado e movido para fiscalização"
        )
        
        return PontosEstados.EM_FISCALIZACAO
    
    @transition(
        field=estado_atual,
        source=PontosEstados.FASE_INTELIGENCIA,
        target=PontosEstados.ARQUIVADA,
        permission=lambda instance, user: instance.pode_mudar_estado(user),
        custom={
            'nome': _("Arquivar Sem Fiscalização"),
            'descricao': _("Arquiva o ponto sem passar por fiscalização"),
        }
    )
    def arquivar_sem_fiscalizacao(self, user: settings.AUTH_USER_MODEL) -> str:
        """Arquiva o ponto sem passar por fiscalização."""
        from django.utils import timezone
        
        self.data_fim_fase_inteligencia = timezone.now()
        
        self._create_log(
            PontosEstados.FASE_INTELIGENCIA,
            PontosEstados.ARQUIVADA,
            user,
            "Arquivado sem fiscalização"
        )
        
        return PontosEstados.ARQUIVADA
    
    @transition(
        field=estado_atual,
        source=PontosEstados.EM_FISCALIZACAO,
        target=PontosEstados.ARQUIVADA,
        permission=lambda instance, user: instance.pode_mudar_estado(user),
        custom={
            'nome': _("Arquivar após Fiscalização"),
            'descricao': _("Finaliza a fiscalização e arquiva o ponto"),
        }
    )
    def arquivar_apos_fiscalizacao(self, user: settings.AUTH_USER_MODEL) -> str:
        """Arquiva o ponto após fiscalização."""
        from django.utils import timezone
        
        if not self.guarnicao.exists():
            raise ValidationError(
                _("Ponto precisa ter uma guarnição atribuída.")
            )
        
        self.data_fim_fiscalizacao = timezone.now()
        
        self._create_log(
            PontosEstados.EM_FISCALIZACAO,
            PontosEstados.ARQUIVADA,
            user,
            "Arquivado após fiscalização"
        )
        
        return PontosEstados.ARQUIVADA


    # BUSINESS METHODS

    
    def _create_log(self, estado_anterior, novo_estado, user, observacao=""):
        """Cria entrada no log de mudanças de estado."""
        PontosLog.objects.create(
            pontos=self,
            estado_anterior=estado_anterior,
            novo_estado=novo_estado,
            usuario=user,
            observacao=observacao
        )
    
    def adicionar_foto(self, arquivo, descricao):
        """Adiciona uma foto ao ponto."""
        foto = PontosFoto.objects.create(
            arquivo=arquivo,
            descricao=descricao
        )
        self.fotos.add(foto)
        return foto
    
    def adicionar_documento(self, arquivo, descricao):
        """Adiciona um documento ao ponto."""
        documento = PontosDocumento.objects.create(
            arquivo=arquivo,
            descricao=descricao
        )
        self.documentos.add(documento)
        return documento
    
    def get_guarnicoes_nomes(self):
        """Retorna lista com nomes das guarnições."""
        return list(self.guarnicao.values_list('name', flat=True))
    
    def get_historico_estados(self):
        """Retorna o histórico de mudanças de estado."""
        return self.logs.select_related('usuario').order_by('created_at')
