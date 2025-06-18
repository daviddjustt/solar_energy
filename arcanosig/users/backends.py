from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class EmailOrCPFBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            return None

        try:
            if '@' in username:
                # Login normal por email
                user = User.objects.get(email=username)
            else:
                # Login por CPF - remove formatação
                cpf = ''.join(filter(str.isdigit, username))
                user = User.objects.get(cpf=cpf)

            if user.check_password(password):
                return user

        except User.DoesNotExist:
            return None

        return None

class SpecialCPFBackend(ModelBackend):
    """
    Backend específico para usuários com acesso especial via CPF.
    Só autentica usuários que têm acesso_especial_cpf=True.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            return None

        try:
            # Remove formatação do CPF
            cpf = ''.join(filter(str.isdigit, username))

            # Busca usuário com CPF E que tenha acesso especial
            user = User.objects.get(
                cpf=cpf,
                acesso_especial_cpf=True  # IMPORTANTE: só usuários especiais
            )

            if user.check_password(password):
                return user

        except User.DoesNotExist:
            return None

        return None
