from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django.contrib.auth import forms as admin_forms
from django.forms import EmailField, CharField, ValidationError # Importar CharField e ValidationError
from django.utils.translation import gettext_lazy as _

# Importar as classes de validação da biblioteca
from validate_docbr import CPF, CNPJ

from .models import User

# Instâncias dos validadores
cpf_validator = CPF()
cnpj_validator = CNPJ()


class UserAdminChangeForm(admin_forms.UserChangeForm):
    # Adicionar o campo cpf_cnpj ao formulário de mudança do admin
    cpf_cnpj = CharField(label=_("CPF ou CNPJ"), max_length=14, required=False)

    class Meta(admin_forms.UserChangeForm.Meta): # type: ignore[name-defined]
        model = User
        # Incluir 'cpf_cnpj' na lista de fields se você quiser que apareça por padrão
        # fields = admin_forms.UserChangeForm.Meta.fields + ("cpf_cnpj",) # Exemplo para adicionar ao fim
        # Ou liste explicitamente todos os campos desejados, incluindo 'cpf_cnpj'
        fields = ("email", "name", "is_active", "is_staff", "is_superuser", "groups", "user_permissions", "cpf_cnpj")
        field_classes = {"email": EmailField}

    def clean_cpf_cnpj(self):
        cpf_cnpj_value = self.cleaned_data.get("cpf_cnpj")
        if cpf_cnpj_value:
            # Remover caracteres não numéricos para validação
            cpf_cnpj_numerico = ''.join(filter(str.isdigit, cpf_cnpj_value))

            if len(cpf_cnpj_numerico) == 11: # Parece um CPF
                if not cpf_validator.validate(cpf_cnpj_numerico):
                    raise ValidationError(_("CPF inválido."))
            elif len(cpf_cnpj_numerico) == 14: # Parece um CNPJ
                 if not cnpj_validator.validate(cpf_cnpj_numerico):
                    raise ValidationError(_("CNPJ inválido."))
            elif cpf_cnpj_numerico: # Se não tem 11 nem 14 dígitos, e não está vazio
                 raise ValidationError(_("CPF ou CNPJ deve conter 11 ou 14 dígitos numéricos."))

        # Retorna o valor limpo (pode ser o numérico ou o original, dependendo da sua preferência)
        # Retornando o numérico para consistência no banco de dados
        return cpf_cnpj_numerico if cpf_cnpj_value else None


class UserAdminCreationForm(admin_forms.AdminUserCreationForm):
    """
    Form for User Creation in the Admin Area.
    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """
    # Adicionar o campo cpf_cnpj ao formulário de criação do admin
    cpf_cnpj = CharField(label=_("CPF ou CNPJ"), max_length=14, required=False)


    class Meta(admin_forms.UserCreationForm.Meta): # type: ignorea[name-defined]
        model = User
        # Incluir 'cpf_cnpj' nos fields
        fields = ("email", "name", "cpf_cnpj") # Adicionado 'name' e 'cpf_cnpj'
        field_classes = {"email": EmailField}
        error_messages = {
            "email": {"unique": _("This email has already been taken.")},
        }

    def clean_cpf_cnpj(self):
        cpf_cnpj_value = self.cleaned_data.get("cpf_cnpj")
        if cpf_cnpj_value:
            cpf_cnpj_numerico = ''.join(filter(str.isdigit, cpf_cnpj_value))

            if len(cpf_cnpj_numerico) == 11:
                if not cpf_validator.validate(cpf_cnpj_numerico):
                    raise ValidationError(_("CPF inválido."))
            elif len(cpf_cnpj_numerico) == 14:
                 if not cnpj_validator.validate(cpf_cnpj_numerico):
                    raise ValidationError(_("CNPJ inválido."))
            elif cpf_cnpj_numerico:
                 raise ValidationError(_("CPF ou CNPJ deve conter 11 ou 14 dígitos numéricos."))

        return cpf_cnpj_numerico if cpf_cnpj_value else None


class UserSignupForm(SignupForm):
    """
    Form that will be rendered on a user sign up section/screen.
    Default fields will be added automatically.
    Check UserSocialSignupForm for accounts created from social.
    """
    # Adicionar o campo cpf_cnpj ao formulário de signup padrão
    # Considere se este campo deve ser obrigatório no signup
    cpf_cnpj = CharField(label=_("CPF ou CNPJ"), max_length=14, required=False) # Altere required=True se for obrigatório

    def clean_cpf_cnpj(self):
        cpf_cnpj_value = self.cleaned_data.get("cpf_cnpj")
        if cpf_cnpj_value:
            cpf_cnpj_numerico = ''.join(filter(str.isdigit, cpf_cnpj_value))

            if len(cpf_cnpj_numerico) == 11:
                if not cpf_validator.validate(cpf_cnpj_numerico):
                    raise ValidationError(_("CPF inválido."))
            elif len(cpf_cnpj_numerico) == 14:
                 if not cnpj_validator.validate(cpf_cnpj_numerico):
                    raise ValidationError(_("CNPJ inválido."))
            elif cpf_cnpj_numerico:
                 raise ValidationError(_("CPF ou CNPJ deve conter 11 ou 14 dígitos numéricos."))
        elif self.fields['cpf_cnpj'].required: # Verifica se o campo é obrigatório mas não foi preenchido
             raise ValidationError(_("Este campo é obrigatório."))


        return cpf_cnpj_numerico if cpf_cnpj_value else None


class UserSocialSignupForm(SocialSignupForm):
    """
    Renders the form when user has signed up using social accounts.
    Default fields will be added automatically.
    See UserSignupForm otherwise.
    """
    # Adicionar o campo cpf_cnpj ao formulário de signup social
    # Geralmente, campos adicionais são solicitados após o signup social inicial
    cpf_cnpj = CharField(label=_("CPF ou CNPJ"), max_length=14, required=False) # Altere required=True se for obrigatório

    def clean_cpf_cnpj(self):
        cpf_cnpj_value = self.cleaned_data.get("cpf_cnpj")
        if cpf_cnpj_value:
            cpf_cnpj_numerico = ''.join(filter(str.isdigit, cpf_cnpj_value))

            if len(cpf_cnpj_numerico) == 11:
                if not cpf_validator.validate(cpf_cnpj_numerico):
                    raise ValidationError(_("CPF inválido."))
            elif len(cpf_cnpj_numerico) == 14:
                 if not cnpj_validator.validate(cpf_cnpj_numerico):
                    raise ValidationError(_("CNPJ inválido."))
            elif cpf_cnpj_numerico:
                 raise ValidationError(_("CPF ou CNPJ deve conter 11 ou 14 dígitos numéricos."))
        elif self.fields['cpf_cnpj'].required:
             raise ValidationError(_("Este campo é obrigatório."))

        return cpf_cnpj_numerico if cpf_cnpj_value else None

