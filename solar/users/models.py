import uuid
import re

# Django imports
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models, transaction
from django.conf import settings
from django.contrib.auth.models import Group # Importar Group

# Constantes para validações
CELULAR_REGEX = r'^\d{11}$'
MAX_IMAGE_SIZE_MB = 7

def validate_cpf(cpf):
    """Valida se o CPF possui 11 dígitos numéricos após limpeza."""
    cpf_cleaned = ''.join(filter(str.isdigit, str(cpf or '')))
    if len(cpf_cleaned) != 11:
        raise ValidationError('CPF deve conter 11 dígitos numéricos.')
    if all(d == cpf_cleaned[0] for d in cpf_cleaned):
        raise ValidationError('CPF inválido.')
    return True


def validate_cnpj(cnpj):
    """Valida se o CNPJ possui 14 dígitos numéricos após limpeza."""
    cnpj_cleaned = ''.join(filter(str.isdigit, str(cnpj or '')))
    if len(cnpj_cleaned) != 14:
        raise ValidationError('CNPJ deve conter 14 dígitos numéricos.')
    if all(d == cnpj_cleaned[0] for d in cnpj_cleaned):
        raise ValidationError('CNPJ inválido.')
    return True

def validate_image_size(image):
    """Valida o tamanho máximo da imagem."""
    if image.file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"O tamanho máximo de arquivo é {MAX_IMAGE_SIZE_MB}MB")

class UserManager(BaseUserManager):
    """Gerenciador de usuários personalizado."""
    
    def create_user(self, email, name, cnpj=None, cpf=None, celular=None, password=None, group_name=None, **extra_fields):
        if not email:
            raise ValueError('O e-mail é obrigatório.')
        
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            name=name.upper() if name else None,
            cnpj=cnpj,
            cpf=cpf,
            celular=celular,
            **extra_fields
        )
        user.set_password(password)

        with transaction.atomic():
            user.full_clean()
            # 🟢 1. Único save() necessário para persitir o usuário e gerar a Primary Key
            user.save(using=self._db)

            # 2. Adiciona o grupo diretamente (o relacionameto M2M opera na tabela intermediária)
            if group_name:
                group, _ = Group.objects.get_or_create(name=group_name)
                user.groups.add(group)

        # 🟢 O segundo user.save() foi removido daqui
        return user

    def create_superuser(self, email, name, celular, password=None, **extra_fields):
        extra_fields.setdefault('is_admin', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        return self.create_user(
            email=email,
            name=name,
            celular=celular,
            password=password,
            group_name='Admin',
            **extra_fields
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
        default=False,
        verbose_name='Ativo'
    )
    is_admin = models.BooleanField(default=False, verbose_name="É Administrador")
    is_tecnico = models.BooleanField(default=False, verbose_name="É Técnico")
    is_cliente = models.BooleanField(default=True, verbose_name="É Cliente")
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
        """
        Normaliza os campos de texto do usuário:
        - Nome: Remove espaços nas extremidades e converte para maiúsculas.
        - CPF, CNPJ e Celular: Mantém apenas dígitos numéricos.
        - Evita strings vazias ("") convertendo-as para None (evita erro no unique=True).
        """
        if self.name:
            self.name = self.name.upper().strip()

        if self.cpf:
            cpf_cleaned = ''.join(filter(str.isdigit, str(self.cpf)))
            self.cpf = cpf_cleaned if cpf_cleaned else None

        if self.cnpj:
            cnpj_cleaned = ''.join(filter(str.isdigit, str(self.cnpj)))
            self.cnpj = cnpj_cleaned if cnpj_cleaned else None

        if self.celular:
            celular_cleaned = ''.join(filter(str.isdigit, str(self.celular)))
            self.celular = celular_cleaned if celular_cleaned else None
    
    def clean(self):
        if not self.celular:
            raise ValidationError({'celular': 'O celular é obrigatório.'})

    def save(self, *args, **kwargs):
        """Salva o usuário após normalizar os campos e sincronizar grupos."""
        self.is_active = True 
        self._normalize_text_fields()
        
        # Sincroniza a flag de Pessoa Jurídica baseada no documento preenchido
        if self.cnpj and not self.cpf:
            self.is_pessoa_juridica = True
        elif self.cpf and not self.cnpj:
            self.is_pessoa_juridica = False

        super().save(*args, **kwargs)
        
        # 🟢 Garante que a sincronização unificada de grupos ocorra APÓS salvar
        self._sync_groups()

    def _sync_groups(self):
        """
        Gerencia todos os grupos de acesso de forma centralizada e sem duplicidade.
        Substitui as funções antigas _update_groups e _assign_to_groups.
        """
        # 1. Busca ou cria os grupos com Nomes Padronizados
        group_admin, _ = Group.objects.get_or_create(name='Admin')
        group_tecnico, _ = Group.objects.get_or_create(name='Técnicos')
        group_cliente, _ = Group.objects.get_or_create(name='Clientes')
        group_pf, _ = Group.objects.get_or_create(name='Clientes PF')
        group_pj, _ = Group.objects.get_or_create(name='Clientes PJ')

        # 2. Sincroniza o perfil Administrador
        if self.is_admin or self.is_superuser:
            self.groups.add(group_admin)
        else:
            self.groups.remove(group_admin)

        # 3. Sincroniza o perfil Técnico
        if self.is_tecnico:
            self.groups.add(group_tecnico)
        else:
            self.groups.remove(group_tecnico)

        # 4. Sincroniza o perfil Cliente e ramificações PF/PJ
        if self.is_cliente:
            self.groups.add(group_cliente)
            if self.is_pessoa_juridica:
                self.groups.add(group_pj)
                self.groups.remove(group_pf)
            else:
                self.groups.add(group_pf)
                self.groups.remove(group_pj)
        else:
            # Remove de todos os grupos de cliente se não for mais cliente
            self.groups.remove(group_cliente, group_pf, group_pj)

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

    @property
    def cnpj_or_cpf_do_cliente(self):
        """Retorna o CNPJ se for PJ, ou o CPF se for PF."""
        if self.is_pessoa_juridica:
            return self.cnpj
        return self.cpf
    
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

    def _assign_to_groups(self):
        """
        Sincroniza os grupos do usuário de acordo com a presença de CPF ou CNPJ.
        """
        group_admin, _ = Group.objects.get_or_create(name='Admin')
        group_tecnico, _ = Group.objects.get_or_create(name='Técnicos')
        group_cliente, _ = Group.objects.get_or_create(name='Clientes')
        group_cliente_pf, _ = Group.objects.get_or_create(name='Clientes PF')
        group_cliente_pj, _ = Group.objects.get_or_create(name='Clientes PJ')

        if self.is_superuser:
            self.groups.add(group_admin)
        elif self.cpf and not self.cnpj:
            # CPF preenchido -> Pessoa Física (is_pessoa_juridica = False)
            self.groups.remove(group_cliente_pj)
            self.groups.add(group_cliente, group_cliente_pf)
        elif self.cnpj and not self.cpf:
            # CNPJ preenchido -> Pessoa Jurídica (is_pessoa_juridica = True)
            self.groups.remove(group_cliente_pf)
            self.groups.add(group_cliente, group_cliente_pj)
        

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
        self.is_admin = False
        self.is_tecnico = True
        self.is_cliente = False
        self.is_pessoa_juridica = False
        self.cnpj = None
        
        # Um único save() que atualiza os campos e dispara a sincronização de grupos do User
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Técnico: {self.get_full_name() or self.email}"


class Cliente(User):
    """
    Perfil de usuário Cliente (Pessoa Física).
    """
    class Meta:
        proxy = True
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        permissions = [
            ('can_view_own_projects', 'Pode visualizar apenas seus próprios projetos'),
            ('cannot_edit_financial_data', 'Não pode editar dados financeiros'),
        ]

    def save(self, *args, **kwargs):
        self.is_admin = False
        self.is_tecnico = False
        self.is_cliente = True
        self.is_pessoa_juridica = False
        self.cnpj = None
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Cliente: {self.get_full_name() or self.email}"


class Empresa(User):
    """
    Perfil de usuário Empresa (Pessoa Jurídica).
    """
    class Meta:
        proxy = True
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        permissions = [
            ('can_view_own_projects', 'Pode visualizar apenas seus próprios projetos'),
            ('cannot_edit_financial_data', 'Não pode editar dados financeiros'),
        ]

    def save(self, *args, **kwargs):
        self.is_admin = False
        self.is_tecnico = False
        self.is_cliente = True
        self.is_pessoa_juridica = True
        self.cpf = None
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Empresa: {self.get_full_name() or self.email}"
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
