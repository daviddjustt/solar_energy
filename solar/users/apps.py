from django.apps import AppConfig
class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'solar.users'
    verbose_name = 'Usuários'
    def ready(self):
        pass 