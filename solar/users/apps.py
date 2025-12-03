from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.dispatch import receiver

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    verbose_name = "Gerenciamento de Usuários"

    def ready(self):
        # Importa o modelo Group aqui para evitar importação circular
        from django.contrib.auth.models import Group
        # Importa o User para o signal, se necessário, mas não para criar grupos
        # from .models import User

        @receiver(post_migrate)
        def create_default_groups(sender, **kwargs):
            if sender.name == 'users': # Garante que o sinal só rode para a sua app 'users'
                Group.objects.get_or_create(name='Admin')
                Group.objects.get_or_create(name='Técnicos')
                Group.objects.get_or_create(name='Clientes')
                Group.objects.get_or_create(name='Clientes PF')
                Group.objects.get_or_create(name='Clientes PJ')
                print("Grupos padrão (Admin, Técnicos, Clientes, Clientes PF, Clientes PJ) verificados/criados.")

