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
    
    def create_user(self, email, name, cpf, celular, password=None, **extra_fields):
        """Cria um usuário com os dados fornecidos."""
        if not email:
            raise ValueError('O usuário deve ter um endereço de email')
        
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            name=name.upper() if name else None,
            cpf=cpf,
            celular=celular,
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
            password=password,
            is_admin=True,
            is_active=True,
            is_superuser=True,  # ADICIONADO: Garantir que is_superuser seja True
        )

class User(AbstractBaseUser, PermissionsMixin):
    """Modelo de usuário para policiais militares."""
    
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
    
    is_active = models.BooleanField(
        default=False,
        verbose_name='Ativo'
    )
    
    is_admin = models.BooleanField(
        default=False,
        verbose_name='Administrador'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em'
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
        if not self.cpf:
            raise ValidationError({'cpf': 'O CPF é obrigatório.'})
        try:
            validate_cpf(self.cpf)
        except ValidationError as e:
            raise ValidationError({'cpf': e})
        if not self.celular:
            raise ValidationError({'celular': 'O celular é obrigatório.'})
    
    def save(self, *args, **kwargs):
        """Salva o usuário após normalizar os campos."""
        self._normalize_text_fields()
        super().save(*args, **kwargs)
    
    # CORREÇÃO PRINCIPAL: is_staff como property
    @property
    def is_staff(self):
        """
        Verifica se o usuário é staff (pode acessar o admin).
        Baseado no campo is_admin.
        """
        return self.is_admin
    
    # OPCIONAL: Setter para is_staff (para compatibilidade)
    @is_staff.setter
    def is_staff(self, value):
        """
        Permite definir is_staff, que na verdade altera is_admin.
        """
        self.is_admin = value

# Resto do código permanece igual...
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
        managed = False

class EmailLog(models.Model):
    """Registra todos os e-mails enviados pelo sistema."""
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
    email_type = models.CharField(max_length=20, choices=EMAIL_TYPES)
    recipient = models.EmailField()
    subject = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
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
