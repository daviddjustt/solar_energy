from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Cria superuser inicial automaticamente'

    def handle(self, *args, **options):
        email = 'admin@solarenergy.com'
        
        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f'ℹ️  Superuser {email} já existe'))
            return
        
        try:
            user = User.objects.create_superuser(
                email=email,
                name='Administrador',
                cpf='12345678900',
                cnpj='12345678000190',
                celular='11987654321',
                password='admin123456'
            )
            self.stdout.write(self.style.SUCCESS(f'✅ Superuser criado: {user.email}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Erro: {e}'))
