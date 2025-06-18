from django import forms
from django.utils.translation import gettext_lazy as _

class ImportUserForm(forms.Form):
    """
    Formulário simples para renderização no Django Admin para a view de importação.
    A validação real dos dados é feita pelo ImportUserSerializer.
    """
    file = forms.FileField(
        label=_("Arquivo"),
        help_text=_("Selecione um arquivo CSV, XLS ou XLSX com os dados dos usuários.")
    )
    send_emails = forms.BooleanField(
        label=_("Enviar E-mails"),
        help_text=_("Marque para enviar e-mails de boas-vindas aos novos usuários."),
        required=False,
        initial=True # Define o valor inicial para o checkbox no template
    )
