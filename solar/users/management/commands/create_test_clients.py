import os
import sys
import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from faker import Faker

User = get_user_model()
fake = Faker('pt_BR')

class Command(BaseCommand):
    help = 'Cria 50 usuários clientes de teste com dados aleatórios e senha padrão.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('🚀 Iniciando a criação de 50 usuários clientes de teste...'))

        password = 'Senha123456'
        created_count = 0

        for i in range(1, 51):
            try:
                is_pessoa_juridica = (i % 2 == 0)

                email = f'cliente_{i}_{fake.uuid4()}@teste.com'
                name = fake.name() if not is_pessoa_juridica else fake.company()
                celular = fake.numerify('###########')

                cpf = None
                cnpj = None

                if is_pessoa_juridica:
                    cnpj = fake.cnpj()
                else:
                    cpf = fake.cpf()

                user = User.objects.create_user(
                    email=email,
                    name=name,
                    cnpj=cnpj,
                    cpf=cpf,
                    celular=celular,
                    password=password,
                    is_pessoa_juridica=is_pessoa_juridica,
                    is_active=True
                )
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✅ Usuário cliente {user.email} ({user.get_display_name()}) criado com sucesso!'))

            except IntegrityError as e:
                self.stderr.write(self.style.WARNING(f'⚠️ Erro de integridade ao criar usuário {email}: {e}. Tentando próximo...'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'❌ Erro inesperado ao criar usuário {email}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'\n🎉 Finalizado! {created_count} usuários clientes de teste criados.'))

