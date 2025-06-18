#       * Os templates de email do Djoser precisam seguir esse padrão de blocos:
#       * subject: Define o assunto do email
#       * text_body: Define a versão em texto simples do corpo do email
#       * html_body: Define a versão HTML do corpo do email

from djoser import email

class ActivationEmail(email.ActivationEmail):
    template_name = 'email/activation.html'

class ConfirmationEmail(email.ConfirmationEmail):
    template_name = 'email/confirmation.html'

class PasswordResetEmail(email.PasswordResetEmail):
    template_name = 'email/password_reset.html'

class PasswordChangedConfirmationEmail(email.PasswordChangedConfirmationEmail):
    template_name = 'email/password_changed_confirmation.html'

class UsernameResetEmail(email.UsernameResetEmail):
    template_name = 'email/username_reset.html'
    
class ImportUserEmail(email.ImportUserEmail):
    template_name = 'email/activation_imports.html'
