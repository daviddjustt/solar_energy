import os
import secrets
import uuid
from datetime import timedelta

# Django Core
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.db.models import Max
from django.core.validators import MinValueValidator
from django.dispatch import Signal
from django.db.models.signals import post_save, post_delete, pre_save
from django.forms.models import model_to_dict

# Simple history 
from simple_history.models import HistoricalRecords

# Choices para o tipo de alteração
CHANGE_TYPE_CHOICES = [
    ('create', 'Criação'),
    ('update', 'Atualização'),
    ('delete', 'Exclusão'),
    ('access', 'Acesso'),
    ('download', 'Download'),
    ('view_pdf', 'Visualização PDF'),
]

def caminho_relatorio_inteligencia(instancia, filename):
    """
    Gera um caminho único para armazenar relatórios de inteligência.
    Garante que cada relatório tenha um identificador único.
    """
    if not instancia.id:
        instancia.id = uuid.uuid4()
    extensao = os.path.splitext(filename)[1]
    novo_nome = f"{instancia.id}{extensao}"
    return os.path.join('relatorios_inteligencia', novo_nome)

def validar_tamanho_pdf(pdf):
    """
    Valida o tamanho máximo do arquivo PDF.
    Implementa fast fail para arquivos grandes.
    """
    TAMANHO_MAXIMO_MB = 100

    # Vai pro final para obter a posição (tamanho em bytes)
    pdf.file.seek(0, 2)
    tamanho_em_bytes = pdf.file.tell()

    # Volta para o início para não interferir na leitura posterior
    pdf.file.seek(0)

    if tamanho_em_bytes > TAMANHO_MAXIMO_MB * 1024 * 1024:
        raise ValidationError(f"Arquivo PDF não pode exceder {TAMANHO_MAXIMO_MB}MB")

class TipoRelatorio(models.TextChoices):
    """Tipos possíveis de relatórios de inteligência."""
    PRELIMINAR = 'PRELIMINAR', 'Preliminar'
    FINAL = 'FINAL', 'Final'

class TipoOcorrencia:
    """Define os tipos de ocorrência para quantitativos de relatórios."""
    HOMICIDIO = "H"
    TENTATIVA_HOMICIDIO = "TH"
    LATROCINIO = "L"
    TENTATIVA_LATROCINIO = "TL"
    FEMINICIDIO = "FEM"
    TENTATIVA_FEMINICIDIO = "TFEM"
    MORTE_INTERVENCAO = "MDI"
    MANDADO_PRISAO = "MP"
    ENCONTRO_CADAVER = "EC"
    APREENSAO_DROGAS = "AP_DROGAS"
    APREENSAO_ARMAS = "AP_ARMAS"
    OCORRENCIA_REPERCUSSAO = "OR"
    OUTRAS_INTERCORRENCIAS = "OI"

    CHOICES = [
        (HOMICIDIO, "Homicídio"),
        (TENTATIVA_HOMICIDIO, "Tentativa de Homicídio"),
        (LATROCINIO, "Latrocínio"),
        (TENTATIVA_LATROCINIO, "Tentativa de Latrocínio"),
        (FEMINICIDIO, "Feminicídio"),
        (TENTATIVA_FEMINICIDIO, "Tentativa de Feminicídio"),
        (MORTE_INTERVENCAO, "Morte Decorrente de Intervenção de Agente do Estado"),
        (MANDADO_PRISAO, "Cumprimento de Mandado De Prisão"),
        (ENCONTRO_CADAVER, "Encontro de Cadáver com Indícios de Violência"),
        (APREENSAO_DROGAS, "Apreensão de Drogas"),
        (APREENSAO_ARMAS, "Apreensão de Armas"),
        (OCORRENCIA_REPERCUSSAO, "Ocorrências de Repercussão"),
        (OUTRAS_INTERCORRENCIAS, "Outras Intercorrências"),
    ]

    @classmethod
    def get_display_name(cls, code):
        """Retorna o nome de exibição para o código fornecido."""
        for c, name in cls.CHOICES:
            if c == code:
                return name
        return None

class RelatorioInteligencia(models.Model):
    """
    Modelo centralizado para armazenamento de relatórios de inteligência.
    Implementa auditoria completa e controle de acesso refinado.
    """
    history = HistoricalRecords()

    # Identificação única e imutável
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Novo campo para entrada manual do número sequencial
    numero = models.PositiveIntegerField(
        verbose_name='Número Sequencial',
        help_text='Número sequencial do relatório (apenas dígitos)',
        validators=[MinValueValidator(1)]
    )

    numero_ano = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        verbose_name='Identificação Completa',
    )

    # Define o tipo do relatório (Final ou Preliminar)
    tipo = models.CharField(
        max_length=15,
        choices=TipoRelatorio.choices,
        default=TipoRelatorio.PRELIMINAR,
        verbose_name='Tipo do relatório',
        help_text='Determina se o relatório é final ou preliminar'
    )

    # Relacionamentos
    analista = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='relatorios_criados',
        verbose_name='Analista',
        help_text='Usuário responsável por produzir o relatório',
        limit_choices_to={'is_sac': True, 'sac_profile': 'ANALISTA'} # Exemplo de filtro
    )
    focal = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='relatorios_focais',
        verbose_name='Focal',
        help_text='Usuário responsável por adicionar o relatório',
        limit_choices_to={'is_sac': True, 'sac_profile': 'FOCAL'} # Exemplo de filtro
    )

    # Armazenamento de documento
    arquivo_pdf = models.FileField(
        upload_to=caminho_relatorio_inteligencia,
        validators=[
            FileExtensionValidator(['pdf']),
            validar_tamanho_pdf
        ],
        verbose_name='Arquivo PDF',
        help_text='Documento PDF do relatório de inteligência'
    )

    # Metadados de rastreamento
    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em'
    )
    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em'
    )

    # Campos para controle de acesso e rastreamento
    quantidade_acessos = models.PositiveIntegerField(
        default=0,
        verbose_name='Número de Acessos'
    )
    ultima_visualizacao = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Última Visualização'
    )

    # Campos de quantitativo
    qtd_homicidio = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Homicídio'
    )
    qtd_tentativa_homicidio = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Tentativa de Homicídio'
    )
    qtd_latrocinio = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Latrocínio'
    )
    qtd_tentativa_latrocinio = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Tentativa de Latrocínio'
    )
    qtd_feminicidio = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Feminicídio'
    )
    qtd_tentativa_feminicidio = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Tentativa de Feminicídio'
    )
    qtd_morte_intervencao = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Morte Decorrente de Intervenção'
    )
    qtd_mandado_prisao = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Cumprimento de Mandado de Prisão'
    )
    qtd_encontro_cadaver = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Encontro de Cadáver'
    )
    qtd_apreensao_drogas = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Apreensão de Drogas'
    )
    qtd_apreensao_armas = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Apreensão de Armas'
    )
    qtd_ocorrencia_repercussao = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Ocorrências de Repercussão'
    )
    qtd_outras_intercorrencias = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Outras Intercorrências'
    )

    class Meta:
        verbose_name = 'Relatório de Inteligência'
        verbose_name_plural = 'Relatórios de Inteligência'
        ordering = ['-criado_em']
        permissions = [
            ("view_confidential_report", "Pode visualizar relatórios confidenciais"),
            ("add_intelligence_report", "Pode adicionar relatórios de inteligência"),
        ]

    def clean(self):
        """
        Validações personalizadas com fast fail.
        """
        # Validações de campos obrigatórios
        if not self.focal:
            raise ValidationError({'focal': 'O campo focal é obrigatório.'})

        # Valida se o número já existe para o mesmo tipo e ano
        ano_atual = timezone.now().year
        if RelatorioInteligencia.objects.filter(
            tipo=self.tipo,
            numero=self.numero,
            criado_em__year=ano_atual
        ).exclude(id=self.id).exists():
            raise ValidationError({
                'numero': f'Já existe um relatório {self.get_tipo_display()} com este número para o ano atual'
            })

    def save(self, *args, **kwargs):
        """
        Sobrescreve o método save para gerar a numeração sequencial com o ano
        e permitir a passagem do usuário para o log customizado.
        """
        # Tenta obter o usuário dos kwargs, se foi passado (ex: form.save(user=request.user))
        # A lógica de log foi movida para o signal post_save.
        # Mantemos a passagem do user aqui caso precise em outro lugar no save.
        user = kwargs.pop('user', None)

        if not self.numero_ano or self.numero_ano == "000/0000":
            ano_atual = timezone.now().year
            ultimo_numero = RelatorioInteligencia.objects.filter(
                criado_em__year=ano_atual
            ).exclude(numero_ano="000/0000").aggregate(Max('numero_ano'))['numero_ano__max']

            if ultimo_numero:
                try:
                    ultimo_numero_int = int(ultimo_numero.split('/')[0])
                    novo_numero = ultimo_numero_int + 1
                except (ValueError, IndexError):
                    novo_numero = 1
            else:
                novo_numero = 1
            self.numero_ano = f"{novo_numero:03d}/{ano_atual}"

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Sobrescreve o método delete para permitir a passagem do usuário.
        A lógica de log foi movida para o signal post_delete.
        """
        user = kwargs.pop('user', None) # Tenta obter o usuário dos kwargs passados para delete()
        super().delete(*args, **kwargs)

    def get_quantitativos_nao_zero(self):
        """Retorna dicionário com quantitativos diferentes de zero."""
        campos_quantitativo = {
            TipoOcorrencia.HOMICIDIO: self.qtd_homicidio,
            TipoOcorrencia.TENTATIVA_HOMICIDIO: self.qtd_tentativa_homicidio,
            TipoOcorrencia.LATROCINIO: self.qtd_latrocinio,
            TipoOcorrencia.TENTATIVA_LATROCINIO: self.qtd_tentativa_latrocinio,
            TipoOcorrencia.FEMINICIDIO: self.qtd_feminicidio,
            TipoOcorrencia.TENTATIVA_FEMINICIDIO: self.qtd_tentativa_feminicidio,
            TipoOcorrencia.MORTE_INTERVENCAO: self.qtd_morte_intervencao,
            TipoOcorrencia.MANDADO_PRISAO: self.qtd_mandado_prisao,
            TipoOcorrencia.ENCONTRO_CADAVER: self.qtd_encontro_cadaver,
            TipoOcorrencia.APREENSAO_DROGAS: self.qtd_apreensao_drogas,
            TipoOcorrencia.APREENSAO_ARMAS: self.qtd_apreensao_armas,
            TipoOcorrencia.OCORRENCIA_REPERCUSSAO: self.qtd_ocorrencia_repercussao,
            TipoOcorrencia.OUTRAS_INTERCORRENCIAS: self.qtd_outras_intercorrencias
        }

    def __str__(self):
        return f"{self.numero_ano} - {self.get_tipo_display()}"

class RelatorioInteligenciaChangeLog(models.Model):
    """Registro de alterações feitas em objetos RelatorioInteligencia."""
    relatorio = models.ForeignKey(
        'RelatorioInteligencia',
        on_delete=models.SET_NULL,
        null=True,
        related_name='change_logs',
        verbose_name='Relatório Alterado'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='report_changes_made',
        verbose_name='Alterado por'
    )
    usuario = models.ForeignKey(  # CAMPO ADICIONAL SOLICITADO
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='report_access_logs',
        verbose_name='Usuário que acessou'
    )
    endereco_ip = models.GenericIPAddressField(  # CAMPO ADICIONAL SOLICITADO
        null=True,
        blank=True,
        verbose_name='Endereço IP'
    )
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name='Data da alteração')
    change_type = models.CharField(
        max_length=20,  # Aumentei para comportar novos tipos
        choices=CHANGE_TYPE_CHOICES,
        verbose_name='Tipo de Alteração'
    )
    field_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Campo alterado'
    )
    old_value = models.TextField(
        blank=True,
        null=True,
        verbose_name='Valor antigo'
    )
    new_value = models.TextField(
        blank=True,
        null=True,
        verbose_name='Valor novo'
    )
    deleted_report_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name='ID do Relatório Deletado'
    )
    duracao_visualizacao = models.DurationField(
        null=True,
        blank=True,
        verbose_name='Duração da Visualização'
    )
    dispositivo = models.CharField(
        max_length=200,  # Aumentei o tamanho
        null=True,
        blank=True,
        verbose_name='Dispositivo'
    )
    navegador = models.CharField(
        max_length=200,  # Aumentei o tamanho
        null=True,
        blank=True,
        verbose_name='Navegador'
    )

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Log de Alteração de Relatório'
        verbose_name_plural = 'Logs de Alterações de Relatórios'

    def __str__(self):
        report_str = str(self.relatorio) if self.relatorio else f"Relatório Deletado (ID: {self.deleted_report_id})" if self.deleted_report_id else "Relatório Deletado"
        user_str = str(self.changed_by or self.usuario) if (self.changed_by or self.usuario) else "Usuário Desconhecido"
        time_str = self.changed_at.strftime('%Y-%m-%d %H:%M:%S') if self.changed_at else "Data Desconhecida"
        change_type_display = dict(CHANGE_TYPE_CHOICES).get(self.change_type, self.change_type)

        if self.change_type == 'update' and self.field_name:
            return f"[{change_type_display}] {report_str} - Campo '{self.field_name}' de '{self.old_value}' para '{self.new_value}' por {user_str} em {time_str}"
        else:
            return f"[{change_type_display}] {report_str} por {user_str} em {time_str}"

# MODELOS DE COMPARTILHAMENTO

class RelatorioCompartilhamento(models.Model):
    """
    Modelo para gerenciar compartilhamentos de relatórios.
    Permite compartilhamento via CPF ou link especial temporário.
    """
    TIPO_CHOICES = [
        ('cpf', 'Compartilhamento via CPF'),
        ('especial', 'Link Especial Temporário'),
    ]

    relatorio = models.ForeignKey(
        RelatorioInteligencia,
        on_delete=models.CASCADE,
        related_name='compartilhamentos'
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='compartilhamentos_criados'
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    token = models.CharField(max_length=64, unique=True, editable=False)

    # Para link especial
    numero_especial = models.CharField(max_length=20, null=True, blank=True)
    senha_especial = models.CharField(max_length=20, null=True, blank=True)

    # Controle de tempo
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField(null=True, blank=True)
    ativo = models.BooleanField(default=True)

    # Logs de acesso
    acessos = models.PositiveIntegerField(default=0)
    ultimo_acesso = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Compartilhamento de Relatório'
        verbose_name_plural = 'Compartilhamentos de Relatórios'
        ordering = ['-criado_em']

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)

        if self.tipo == 'especial' and not self.numero_especial:
            self.numero_especial = self._gerar_numero_especial()
            self.senha_especial = self._gerar_senha_especial()
            self.expira_em = timezone.now() + timedelta(hours=24)

        super().save(*args, **kwargs)

    def _gerar_numero_especial(self):
        """Gera número especial de 11 dígitos"""
        return ''.join([str(secrets.randbelow(10)) for _ in range(11)])

    def _gerar_senha_especial(self):
        """Gera senha especial alfanumérica"""
        return secrets.token_urlsafe(8)[:8]

    def is_valido(self):
        """Verifica se o compartilhamento ainda é válido"""
        if not self.ativo:
            return False
        if self.expira_em and timezone.now() > self.expira_em:
            return False
        return True

    def registrar_acesso(self):
        """Registra um acesso ao compartilhamento"""
        self.acessos += 1
        self.ultimo_acesso = timezone.now()
        self.save(update_fields=['acessos', 'ultimo_acesso'])

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.relatorio.numero_ano}"

class CompartilhamentoAcesso(models.Model):
    """Log de acessos aos compartilhamentos"""
    compartilhamento = models.ForeignKey(
        RelatorioCompartilhamento,
        on_delete=models.CASCADE,
        related_name='logs_acesso'
    )
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    sucesso = models.BooleanField(default=False)
    erro = models.TextField(null=True, blank=True)
    acessado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-acessado_em']

    def __str__(self):
        status = "SUCESSO" if self.sucesso else "FALHA"
        return f"{status} {self.compartilhamento} - {self.ip_address}"

# SIGNALS PARA LOGS
def capture_pre_save_instance(sender, instance, **kwargs):
    """Captura o estado do objeto antes de ser salvo para comparação posterior."""
    if instance.pk:
        try:
            instance._pre_save_instance = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._pre_save_instance = None
    else:
        instance._pre_save_instance = None

def log_relatorio_save(sender, instance, created, **kwargs):
    """Registra a criação ou atualização de um RelatorioInteligencia."""
    user = kwargs.get('user', None)

    if created:
        RelatorioInteligenciaChangeLog.objects.create(
            relatorio=instance,
            changed_by=user,
            change_type='create',
        )
    else:
        old_instance = getattr(instance, '_pre_save_instance', None)

        if old_instance:
            exclude_fields = [
                'id', # PK do RelatorioInteligencia
                'criado_em',
                'atualizado_em',
                'quantidade_acessos',
                'ultima_visualizacao',
                'history_id',
                'history_date',
                'history_change_reason',
                'history_user'
            ]
            old_data = model_to_dict(old_instance, exclude=exclude_fields)
            new_data = model_to_dict(instance, exclude=exclude_fields)

            # Itera sobre os campos e compara valores
            for field_name, new_value in new_data.items():
                 old_value = old_data.get(field_name)
                 if old_value != new_value:
                     old_value_str = str(old_value) if old_value is not None else 'Nulo'
                     new_value_str = str(new_value) if new_value is not None else 'Nulo'

                     if field_name in ['analista', 'focal']:
                         try:
                             old_user = sender._meta.get_field(field_name).remote_field.model.objects.get(pk=old_value) if old_value else None
                             old_value_str = str(old_user) if old_user else 'Nulo'
                         except Exception:
                             pass

                         try:
                             new_user = sender._meta.get_field(field_name).remote_field.model.objects.get(pk=new_value) if new_value else None
                             new_value_str = str(new_user) if new_user else 'Nulo'
                         except Exception:
                             pass

                     RelatorioInteligenciaChangeLog.objects.create(
                         relatorio=instance,
                         changed_by=user,
                         change_type='update',
                         field_name=field_name,
                         old_value=old_value_str,
                         new_value=new_value_str,
                     )

        if hasattr(instance, '_pre_save_instance'):
            del instance._pre_save_instance

# Signal para registrar exclusão
def log_relatorio_delete(sender, instance, **kwargs):
    """Registra a exclusão de um RelatorioInteligencia."""
    user = kwargs.get('user', None)

    RelatorioInteligenciaChangeLog.objects.create(
        changed_by=user,
        change_type='delete',
        deleted_report_id=instance.id
    )

pre_save.connect(capture_pre_save_instance, sender=RelatorioInteligencia)
post_save.connect(log_relatorio_save, sender=RelatorioInteligencia)
post_delete.connect(log_relatorio_delete, sender=RelatorioInteligencia)

