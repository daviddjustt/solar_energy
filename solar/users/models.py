import uuid
import re

# Django imports
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.conf import settings
from django.contrib.auth.models import Group # Importar Group

# Constantes para validações
CELULAR_REGEX = r'^\d{11}$'
MAX_IMAGE_SIZE_MB = 7

def validate_cpf(cpf):
    cpf_pattern = r'^\d{3}\.\d{3}\.\d{3}/\d{2}$'
    """Valida o cpf de forma simplificada."""
    cpf = ''.join(filter(str.isdigit, cpf))
    if len(cpf) != 11:
        raise ValidationError('cpf deve conter 18 dígitos')
    if all(d == cpf[0] for d in cpf):
        raise ValidationError('cpf inválido')
    
    return bool(re.match(cpf_pattern, cpf))

def validate_cnpj(cnpj):
    cnpj_pattern = r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$'
    """Valida o cnpj de forma simplificada."""
    cnpj = ''.join(filter(str.isdigit, cnpj))
    if len(cnpj) != 14:
        raise ValidationError('cnpj deve conter 18 dígitos')
    if all(d == cnpj[0] for d in cnpj):
        raise ValidationError('cnpj inválido')
    
    return bool(re.match(cnpj_pattern, cnpj))

def validate_image_size(image):
    """Valida o tamanho máximo da imagem."""
    if image.file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"O tamanho máximo de arquivo é {MAX_IMAGE_SIZE_MB}MB")

class UserManager(BaseUserManager):
    """Gerenciador de usuários personalizado."""
    
    def create_user(self, email, name, cnpj, cpf, celular=None, password=None, **extra_fields):

            user = self.model(
                email=email,
                name=name.upper() if name else None,
                cnpj=cnpj,
                cpf=cpf,
                celular=celular,
                is_cliente=False,
                **extra_fields
            )
            user.set_password(password)
            user.save(using=self._db)
            return user

    def create_superuser(self, email, name, cnpj, cpf, celular, password=None):
            return self.create_user(
                email=email,
                name=name,
                cnpj=cnpj,
                cpf=cpf,
                celular=celular,
                password=password,
                is_admin=True,
                is_active=True,
                is_superuser=True,
            )
    
class User(AbstractBaseUser, PermissionsMixin):
    """Modelo de usuário para policiais militares."""
    
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="uuid")
    
    email = models.EmailField(
        max_length=255,
        unique=True,
        verbose_name='Email'
    )
    
    name = models.CharField(
        max_length=255,
        verbose_name='Nome'
    )
    
    cnpj = models.CharField(
        max_length=18, # # 18 dígitos + 4 caracteres de formatação (XX.XXX.XXX/XXXX-XX)
        unique=True,
        verbose_name='cnpj',
        null=True,
        blank=True,
    )
    cpf = models.CharField(
        max_length=14, # 11 dígitos + 3 caracteres de formatação (XXX.XXX.XXX-XX)
        unique=True,
        verbose_name='CPF',
        null=True,
        blank=True,
    )
    celular = models.CharField(
        max_length=11,
        verbose_name='Celular'
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name='Ativo'
    )
    is_admin = models.BooleanField(default=False, verbose_name="É Administrador")
    is_tecnico = models.BooleanField(default=False, verbose_name="É Técnico")
    is_cliente = models.BooleanField(default=False, verbose_name="É Cliente")
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em'
    )
    is_pessoa_juridica = models.BooleanField(default=False, verbose_name="É Pessoa Jurídica")
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'cnpj', 'celular', 'cpf', 'is_pessoa_juridica']
    
    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'
    
    def __str__(self):
        return self.get_display_name()
    
    def get_display_name(self):
        """Retorna o nome de exibição do usuário."""
        return f"{self.name} - {self.cnpj}"
    
    def _normalize_text_fields(self):
        """Normaliza os campos de texto."""
        if self.name:
            self.name = self.name.upper()
        if self.cnpj:
            self.cnpj = ''.join(filter(str.isdigit, self.cnpj))
        if self.celular:
            self.celular = ''.join(filter(str.isdigit, self.celular))
    
    def clean(self):
        if not self.celular:
            raise ValidationError({'celular': 'O celular é obrigatório.'})
    
    def save(self, *args, **kwargs):
        """Salva o usuário após normalizar os campos."""
        self._normalize_text_fields()
        super().save(*args, **kwargs)
        self._update_groups()


    def get_full_name(self):
            """Retorna o nome completo do usuário."""
            return self.name.strip()

    def get_short_name(self):
            """Retorna o primeiro nome ou uma versão curta do nome do usuário."""
            return self.name.split(' ')[0] if self.name else ''
    
    def _update_groups(self):
        adm_group, _ = Group.objects.get_or_create(name='Administradores')
        tecnico_group, _ = Group.objects.get_or_create(name='Tecnicos')
        cliente_group, _ = Group.objects.get_or_create(name='Clientes')

        # Lógica para adicionar/remover o usuário dos grupos com base nas flags
        if self.is_admin:
            self.groups.add(adm_group)
        else:
            self.groups.remove(adm_group)

        if self.is_tecnico:
            self.groups.add(tecnico_group)
        else:
            self.groups.remove(tecnico_group)

        if self.is_cliente:
            self.groups.add(cliente_group)
        else:
            self.groups.remove(cliente_group)
        
    @property
    def is_admin(self):
        return self.is_staff or self.is_superuser

    @property
    def is_tecnico(self):
        # Assumindo que 'Tecnicos' é um grupo
        return self.groups.filter(name='Tecnicos').exists()

    @property
    def is_cliente(self):
        # Assumindo que 'Clientes' é um grupo
        return self.groups.filter(name='Clientes').exists()

class Tecnico(User):
    """
    Perfil de usuário Técnico. Pode ver todos os projetos, mas não edita campos financeiros.
    """
    class Meta:
        proxy = True
        verbose_name = 'Técnico'
        verbose_name_plural = 'Técnicos'
        permissions = [
            ('can_view_financial_data', 'Pode visualizar dados financeiros'),
            ('cannot_edit_financial_data', 'Não pode editar dados financeiros'),
        ]
    
    def save(self, *args, **kwargs):
        # Garante que o Técnico seja staff (pode acessar o admin)
        if (self==True):
            self.is_staff = False
            self.is_admin = False
            self.is_tecnico = True
            self.is_cliente = False
            super().save(update_fields=['is_staff'])
            super().save(update_fields=['is_admin'])
            super().save(update_fields=['is_tecnico'])
            super().save(update_fields=['cliente'])
        
        # Gaante que a Empresa é uma pessoa jurídica
        if self.is_pessoa_juridica is True:
            self.is_pessoa_juridica = False
            super().save(update_fields=['is_pessoa_juridica'])
            self.cnpj = None
            super().save(update_fields=['cnpj'])
        
        # Adicionar ao grupo 'Tecnicos'
        tecnico_group, created = Group.objects.get_or_create(name='Tecnicos')
        self.groups.add(tecnico_group)
        
        # Remover de 'Clientes' se estiver lá (para garantir exclusividade de papel)
        cliente_group = Group.objects.filter(name='Clientes').first()
        if cliente_group and self.groups.filter(name='Clientes').exists():
            self.groups.remove(cliente_group)
            

    def __str__(self):
        return f"Técnico: {self.get_full_name() or self.username}"

class Cliente(Tecnico):
    """
    Perfil de usuário Cliente. Não pode editar campos financeiros e
    só pode acessar seus próprios projetos.
    """
    class Meta:
        proxy = True
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        permissions = [
            ('can_view_own_projects', 'Pode visualizar apenas seus próprios projetos'),
            ('cannot_edit_financial_data', 'Não pode editar dados financeiros'), # Redundante, mas explícito
        ]

    def save(self, *args, **kwargs):
        # Primeiro, chama o save de Tecnico (super()), que adiciona ao grupo 'Tecnicos' e define is_staff=True
        super().save(*args, **kwargs) 
        
        # Agora, remove de 'Tecnicos' e adiciona a 'Clientes'
        tecnico_group = Group.objects.filter(name='Tecnicos').first()
        if tecnico_group and self.groups.filter(name='Tecnicos').exists():
            self.groups.remove(tecnico_group)
            
        cliente_group, created = Group.objects.get_or_create(name='Clientes')
        self.groups.add(cliente_group)
        
        # Garante que o Cliente NÃO seja staff
        if (self==True):
            self.is_staff = False
            self.is_admin = False
            self.is_tecnico = False
            self.is_cliente = True
            super().save(update_fields=['is_staff'])
            super().save(update_fields=['is_admin'])
            super().save(update_fields=['is_tecnico'])
            super().save(update_fields=['cliente'])
        
        # Gaante que o Cliente é uma pessoa física
        if self.is_pessoa_juridica is True:
            self.is_pessoa_juridica = False
            super().save(update_fields=['is_pessoa_juridica'])
            self.cnpj = None
            super().save(update_fields=['cnpj'])

    def __str__(self):
        return f"Cliente: {self.get_full_name() or self.username}"

class Empresa(Cliente):
    """
    Perfil de usuário Empresa. Herdado de Cliente.
    Pode acessar apenas seus próprios projetos e não edita campos financeiros.
    """
    class Meta:
        proxy = True
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        permissions = [
            ('can_view_own_projects', 'Pode visualizar apenas seus próprios projetos'),
            ('cannot_edit_financial_data', 'Não pode editar dados financeiros'), # Redundante, mas explícito
        ]

    def save(self, *args, **kwargs):
        # Primeiro, chama o save de Cliente (super()), que adiciona ao grupo 'Clientes' e define is_staff=False
        super().save(*args, **kwargs) 
        
        if (self==True):
            self.is_staff = False
            self.is_admin = False
            self.is_tecnico = False
            self.is_cliente = True
            super().save(update_fields=['is_staff'])
            super().save(update_fields=['is_admin'])
            super().save(update_fields=['is_tecnico'])
            super().save(update_fields=['cliente'])
        
        # Gaante que a Empresa é uma pessoa jurídica
        if self.is_pessoa_juridica is False:
            self.is_pessoa_juridica = True
            super().save(update_fields=['is_pessoa_juridica'])
            self.cpf = None
            super().save(update_fields=['cpf'])

    def __str__(self):
        return f"Empresa: {self.get_full_name() or self.username}"

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
