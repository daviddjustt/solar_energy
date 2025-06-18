# Python standard library imports
import os
import uuid
from datetime import datetime
# Django imports
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, FileExtensionValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.conf import settings

# Constantes para validações
CPF_REGEX = r'^\d{11}$'
CELULAR_REGEX = r'^\d{11}$'
MAX_IMAGE_SIZE_MB = 7

class PatentChoices(models.TextChoices):
    """Opções de patentes para policiais militares."""
    SOLDADO = 'SOLDADO', 'Soldado'
    CABO = 'CABO', 'Cabo'
    SARGENTO = 'SARGENTO', 'Sargento'
    SUBTENENTE = 'SUBTENENTE', 'Subtenente'
    TENENTE = 'TENENTE', 'Tenente'
    CAPITAO = 'CAPITAO', 'Capitão'
    MAJOR = 'MAJOR', 'Major'
    TENENTE_CORONEL = 'TENENTE_CORONEL', 'Tenente Coronel'
    CORONEL = 'CORONEL', 'Coronel'

class SacProfileChoices(models.TextChoices):
    """Perfis dentro do SAC."""
    SEM_ACESSO = 'SEM_ACESSO', 'Sem Acesso'
    LEITOR = 'LEITOR', 'Leitor'
    ANALISTA = 'ANALISTA', 'Analista'
    FOCAL = 'FOCAL', 'Focal'

def user_photo_path(instance, filename):
    """Gera o caminho para armazenar a foto do usuário."""
    if not instance.id:
        instance.id = uuid.uuid4()
    ext = os.path.splitext(filename)[1]
    new_filename = f"{instance.id}{ext}"
    return os.path.join('user_photos', new_filename)

def validate_cpf(cpf):
    """Valida o CPF de forma simplificada."""
    cpf = ''.join(filter(str.isdigit, cpf))
    if len(cpf) != 11:
        raise ValidationError('CPF deve conter 11 dígitos')
    if all(d == cpf[0] for d in cpf):
        raise ValidationError('CPF inválido')
    return True

def validate_image_size(image):
    """Valida o tamanho máximo da imagem."""
    if image.file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"O tamanho máximo de arquivo é {MAX_IMAGE_SIZE_MB}MB")

class UserManager(BaseUserManager):
    """Gerenciador de usuários personalizado."""
    def create_user(self, email, name, cpf, celular, password=None, patent=None, is_sac=False, sac_profile=None, acesso_especial_cpf=True, **extra_fields):
        """Cria um usuário com os dados fornecidos."""
        if not email:
            raise ValueError('O usuário deve ter um endereço de email')
        email = self.normalize_email(email)
        extra_fields.setdefault('is_operacoes', False)  # Define valor padrão para is_operacoes
        # Define valores padrão para patent se não fornecido
        if patent is None:
            patent = PatentChoices.SOLDADO
        # Define sac_profile como SEM_ACESSO se is_sac=False
        if not is_sac:
            sac_profile = SacProfileChoices.SEM_ACESSO
        user = self.model(
            email=email,
            name=name.upper() if name else None,
            cpf=cpf,
            celular=celular,
            patent=patent,
            is_sac=is_sac,
            sac_profile=sac_profile,
            acesso_especial_cpf=acesso_especial_cpf,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, cpf, celular, password=None):
        """Cria um superusuário."""
        return self.create_user(
            email=email,
            name=name,
            cpf=cpf,
            celular=celular,
            patent=PatentChoices.CORONEL,
            password=password,
            is_admin=True,
            is_active=True,
            is_superuser=True,  # Explicitamente define como superuser
            is_operacoes=True,  # Superusuário: is_operacoes = True
            is_sac=True,  # Define is_sac como True para superusuário
            sac_profile=SacProfileChoices.FOCAL,  # Define o perfil SAC como "Focal" por padrão
            acesso_especial_cpf=True  # Garante que superuser tenha acesso especial por CPF
        )

class User(AbstractBaseUser, PermissionsMixin):
    """Modelo de usuário para policiais militares."""
    # Adicionar o HistoricalRecords para auditoria

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(
        max_length=255,
        unique=True,
        verbose_name='Email'
    )
    name = models.CharField(
        max_length=255,
        verbose_name='Nome'
    )
    cpf_validator = RegexValidator(
        regex=CPF_REGEX,
        message='CPF inválido'
    )
    cpf = models.CharField(
        max_length=11,
        validators=[cpf_validator],
        unique=True,
        verbose_name='CPF'
    )
    celular_validator = RegexValidator(
        regex=CELULAR_REGEX,
        message='Celular inválido'
    )
    celular = models.CharField(
        max_length=11,
        validators=[celular_validator],
        verbose_name='Celular'
    )
    photo = models.ImageField(
        upload_to=user_photo_path,
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png']),
            validate_image_size
        ],
        verbose_name='Foto'
    )
    patent = models.CharField(
        max_length=20,
        choices=PatentChoices.choices,
        default=PatentChoices.SOLDADO,
        verbose_name='Patente'
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name='Ativo'
    )
    is_admin = models.BooleanField(
        default=False,
        verbose_name='Administrador'
    )
    is_operacoes = models.BooleanField(
        default=False,
        verbose_name='Operações'
    )
    is_sac = models.BooleanField(
        default=False,
        verbose_name='É SAC'
    )
    sac_profile = models.CharField(
        max_length=10,
        choices=SacProfileChoices.choices,
        null=True,
        blank=True,
        verbose_name='Perfil SAC'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em'
    )

    # Campos de aceso via CPF

    acesso_especial_cpf = models.BooleanField(
        default=True,
        verbose_name='Acesso Especial via CPF',
        help_text='Usuário pode fazer login via link especial usando apenas CPF'
    )

    primeiro_acesso_especial = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Primeiro Acesso Especial'
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'cpf', 'celular']

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self):
        """Retorna o nome de exibição do usuário."""
        return f"{self.name} - {self.cpf}"

    def _normalize_text_fields(self):
        """Normaliza os campos de texto."""
        if self.name:
            self.name = self.name.upper()
        if self.cpf:
            self.cpf = ''.join(filter(str.isdigit, self.cpf))
        if self.celular:
            self.celular = ''.join(filter(str.isdigit, self.celular))

    def clean(self):
        """Valida o usuário antes de salvar."""
        # Validações dos campos obrigatórios
        if not self.cpf:
            raise ValidationError({'cpf': 'O CPF é obrigatório.'})
        try:
            validate_cpf(self.cpf)
        except ValidationError as e:
            raise ValidationError({'cpf': e})
        if not self.celular:
            raise ValidationError({'celular': 'O celular é obrigatório.'})
        if self.is_sac and not self.sac_profile:
            raise ValidationError({'sac_profile': 'Perfil SAC é obrigatório se o usuário for SAC.'})

    def save(self, *args, **kwargs):
        """Salva o usuário após normalizar os campos."""
        self._normalize_text_fields()
        super().save(*args, **kwargs)

    @property
    def is_staff(self):
        """Verifica se o usuário é staff."""
        return self.is_admin

    @property
    def is_superuser_by_admin(self):
        """Verifica se o usuário é superusuário.
        Nota: isso é complementar à flag is_superuser da PermissionsMixin."""
        return self.is_admin

class UserExport(User):
    class Meta:
        proxy = True
        verbose_name = ("Exportação de Usuários")
        verbose_name_plural = ("Exportações de Usuários")

class UserImport(models.Model):
    class Meta:
        verbose_name = ("Importação de Usuários")
        verbose_name_plural = ("Importação de Usuários")
        app_label = 'users'
        managed = False # Modelo proxy: não cria tabela

class EmailLog(models.Model):
    """
    Registra todos os e-mails enviados pelo sistema.
    """
    STATUS_CHOICES = (
        ('sent', 'Enviado'),
        ('failed', 'Falhou'),
        ('pending', 'Pendente'),
    )
    EMAIL_TYPES = (
        ('welcome', 'Boas-vindas'),
        ('password_reset', 'Redefinição de Senha'),
        ('notification', 'Notificação'),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_logs'
    )
    email_type = models.CharField(
        max_length=20,
        choices=EMAIL_TYPES
    )
    recipient = models.EmailField()
    subject = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'Log de E-mail'
        verbose_name_plural = 'Logs de E-mails'

    def __str__(self):
        return f"{self.email_type} para {self.recipient} ({self.status})"

class UserChangeLog(models.Model):
    """Registro de alterações feitas em usuários."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='change_logs',
        verbose_name='Usuário alterado'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='changes_made',
        verbose_name='Alterado por'
    )
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name='Data da alteração')
    field_name = models.CharField(max_length=100, verbose_name='Campo alterado')
    old_value = models.TextField(blank=True, null=True, verbose_name='Valor antigo')
    new_value = models.TextField(blank=True, null=True, verbose_name='Valor novo')

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Log de Alteração de Usuário'
        verbose_name_plural = 'Logs de Alterações de Usuários'

    def __str__(self):
        return f"{self.user} - {self.field_name} - {self.changed_at}"