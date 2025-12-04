import uuid
import re

# Django imports
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models, transaction
from django.conf import settings
from django.contrib.auth.models import Group # Importar Group
from django.utils import timezone
# Constantes para validações
from solar.choices import (
    CelularRegex,
    MaxImageSize
)

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

class UserManager(BaseUserManager):
    """
    Gerenciador de usuários customizado para o modelo User.
    Define métodos para criar usuários e superusuários, e adicioná-los a grupos.
    """
    def _create_user(self, email, password, name, celular, cpf=None, cnpj=None, group_name=None, **extra_fields):
        """
        Cria e salva um usuário com o email, senha, nome, celular e adiciona ao grupo fornecido.
        """
        if not email:
            raise ValueError('O endereço de email deve ser fornecido.')
        if not name:
            raise ValueError('O nome deve ser fornecido.')
        if not celular:
            raise ValueError('O número de celular deve ser fornecido.')

        email = self.normalize_email(email)

        # Validação de celular
        if celular and not models.RegexValidator(regex=CelularRegex.REGEX)(celular):
             raise ValidationError('Celular inválido. Formato esperado: DDNNNNNNNNN (ex: 11987654321).')

        user = self.model(
            email=email,
            name=name,
            celular=celular,
            cpf=cpf,
            cnpj=cnpj,
            **extra_fields
        )
        user.set_password(password)

        with transaction.atomic(): # Garante que a criação do usuário e adição ao grupo sejam atômicas
            user.full_clean() # Executa as validações do modelo (incluindo CPF/CNPJ)
            user.save(using=self._db)

            if group_name:
                try:
                    group = Group.objects.get(name=group_name)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    raise ValueError(f"O grupo '{group_name}' não existe.")

        return user

    def create_user(self, email, password=None, name=None, celular=None, cpf=None, cnpj=None, group_name='Clientes PF', **extra_fields):
        """
        Cria e salva um usuário normal (cliente PF por padrão).
        """
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('is_active', True)

        # Se o grupo for 'Clientes PJ', CNPJ é obrigatório e CPF deve ser None
        if group_name == 'Clientes PJ':
            if not cnpj:
                raise ValueError('CNPJ é obrigatório para clientes PJ.')
            cpf = None # Garante que CPF seja None para PJ
        elif group_name == 'Clientes PF':
            if not cpf:
                raise ValueError('CPF é obrigatório para clientes PF.')
            cnpj = None # Garante que CNPJ seja None para PF
        elif group_name == 'Técnicos':
            cpf = None
            cnpj = None
        else:
            raise ValueError(f"Grupo '{group_name}' não é um grupo de usuário válido para criação de usuário normal.")

        return self._create_user(
            email,
            password,
            name,
            celular,
            cpf=cpf,
            cnpj=cnpj,
            group_name=group_name,
            **extra_fields
        )

    def create_superuser(self, email, password, name, celular, **extra_fields):
        """
        Cria e salva um superusuário.
        Um superusuário é automaticamente staff e superuser.
        Não é adicionado a nenhum grupo de papel por padrão, mas pode ser se necessário.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        # Superusuários não precisam de CPF/CNPJ/celular obrigatórios para o Django,
        # mas você pode forçar isso aqui se quiser.
        # Pelas suas memórias, superusuário requer cpf/cnpj e celular.
        if not name:
            raise ValueError('Superuser must have a name.')
        if not celular:
            raise ValueError('Superuser must have a celular.')

        # Para superusuários, não vamos forçar CPF/CNPJ aqui,
        # pois eles podem ser "internos" e não se encaixar em PF/PJ.
        # Se um superusuário precisar ser também um cliente (PF/PJ),
        # ele deve ser adicionado ao grupo correspondente após a criação.
        cpf = extra_fields.pop('cpf', None)
        cnpj = extra_fields.pop('cnpj', None)

        return self._create_user(
            email,
            password,
            name,
            celular,
            cpf=cpf,
            cnpj=cnpj,
            group_name=None, # Superusuário não é adicionado a um grupo de papel por padrão
            **extra_fields
        )

class User(AbstractBaseUser, PermissionsMixin):
    """
    Modelo de usuário customizado que suporta login com email e gerencia
    papéis através do sistema de grupos do Django.
    Usa UUID como chave primária.
    """
    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="ID Único do Usuário"
    )
    email = models.EmailField(
        verbose_name='Endereço de email',
        max_length=255,
        unique=True,
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Nome Completo"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Ativo",
        help_text="Indica se o usuário deve ser tratado como ativo. Desmarque em vez de deletar contas."
    )
    is_staff = models.BooleanField( # Necessário para acessar o admin do Django
        default=False,
        verbose_name="Status de Staff",
        help_text="Indica se o usuário pode fazer login neste site de administração."
    )
    # is_admin, is_tecnico, is_cliente, is_pessoa_juridica serão removidos
    # e sua lógica será substituída por grupos.

    cpf = models.CharField(
        max_length=11,
        unique=True,
        blank=True,
        null=True,
        verbose_name="CPF",
        help_text="Cadastro de Pessoa Física (apenas números)."
    )
    cnpj = models.CharField(
        max_length=14,
        unique=True,
        blank=True,
        null=True,
        verbose_name="CNPJ",
        help_text="Cadastro Nacional da Pessoa Jurídica (apenas números)."
    )
    celular_validator = RegexValidator(
        regex=CelularRegex.REGEX,
        message='Celular inválido. Formato esperado: DDNNNNNNNNN (ex: 11987654321).'
    )
    celular = models.CharField(
        max_length=11,
        validators=[celular_validator],
        blank=True,
        null=True,
        verbose_name="Número de Celular"
    )

    date_joined = models.DateTimeField(
        default=timezone.now,
        verbose_name="Data de Cadastro"
    )

    USERNAME_FIELD = 'email'
    # REQUIRED_FIELDS agora só precisa de 'name' e 'celular',
    # pois CPF/CNPJ serão validados com base nos grupos e não são sempre obrigatórios para todos os usuários.
    REQUIRED_FIELDS = ['name', 'celular']

    objects = UserManager()

    class Meta:
        verbose_name = ('usuário')
        verbose_name_plural = ('usuários')
        ordering = ['email']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.name if self.name else self.email

    def get_short_name(self):
        return self.name if self.name else self.email.split('@')[0]

    # Métodos para verificar o papel do usuário através dos grupos
    @property
    def is_admin(self):
        """Um usuário é admin se for um superusuário."""
        return self.is_superuser

    @property
    def is_tecnico(self):
        """Um usuário é técnico se pertencer ao grupo 'Técnicos'."""
        return self.groups.filter(name='Técnicos').exists()

    @property
    def is_cliente(self):
        """Um usuário é cliente se pertencer ao grupo 'Clientes PF' ou 'Clientes PJ'."""
        return self.groups.filter(name__in=['Clientes PF', 'Clientes PJ']).exists()

    @property
    def is_pessoa_juridica(self):
        """Um cliente é PJ se pertencer ao grupo 'Clientes PJ'."""
        return self.groups.filter(name='Clientes PJ').exists()

    @property
    def is_pessoa_fisica(self):
        """Um cliente é PF se pertencer ao grupo 'Clientes PF'."""
        return self.groups.filter(name='Clientes PF').exists()

    def clean(self):
        super().clean()
        # A validação de CPF/CNPJ agora depende dos grupos
        if self.is_pessoa_juridica:
            if not self.cnpj:
                raise models.ValidationError({'cnpj': 'CNPJ é obrigatório para Pessoa Jurídica.'})
            if self.cpf:
                raise models.ValidationError({'cpf': 'CPF deve ser vazio para Pessoa Jurídica.'})
        elif self.is_pessoa_fisica: # Se for PF
            if not self.cpf:
                raise models.ValidationError({'cpf': 'CPF é obrigatório para Pessoa Física.'})
            if self.cnpj:
                raise models.ValidationError({'cnpj': 'CNPJ deve ser vazio para Pessoa Física.'})
        else: # Para usuários que não são clientes (ex: Técnicos, Superusuários sem grupo cliente)
            if self.cpf or self.cnpj:
                raise models.ValidationError({'cpf': 'CPF/CNPJ deve ser vazio para usuários que não são clientes.'})

        # Validação de unicidade para CPF/CNPJ (já garantida por unique=True, mas bom ter aqui também)
        if self.cpf and User.objects.filter(cpf=self.cpf).exclude(uuid=self.uuid).exists():
            raise models.ValidationError({'cpf': 'Já existe um usuário com este CPF.'})
        if self.cnpj and User.objects.filter(cnpj=self.cnpj).exclude(uuid=self.uuid).exists():
            raise models.ValidationError({'cnpj': 'Já existe um usuário com este CNPJ.'})
        
    def _assign_to_groups(self):
        """
        Atribui o usuário aos grupos 'Técnicos', 'Clientes', 'Clientes PF' ou 'Clientes PJ'
        com base nos campos CPF/CNPJ.
        """
        # Garante que os grupos existam
        group_admin, _ = Group.objects.get_or_create(name='Admin')
        group_tecnico, _ = Group.objects.get_or_create(name='Técnicos')
        group_cliente, _ = Group.objects.get_or_create(name='Clientes')
        group_cliente_pf, _ = Group.objects.get_or_create(name='Clientes PF')
        group_cliente_pj, _ = Group.objects.get_or_create(name='Clientes PJ')

        # Limpa associações anteriores para evitar duplicação ou grupos incorretos
        self.groups.remove(group_admin, group_tecnico, group_cliente, group_cliente_pf, group_cliente_pj)

        if self.is_superuser:
            self.groups.add(group_admin)
        elif self.cpf and not self.cnpj: # É Pessoa Física
            self.groups.add(group_cliente, group_cliente_pf)
        elif self.cnpj and not self.cpf: # É Pessoa Jurídica
            self.groups.add(group_cliente, group_cliente_pj)

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
