import os
import sys
import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from faker import Faker

User = get_user_model()
fake = Faker('pt_BR') # Usar localidade brasileira para dados mais relevantes

class Command(BaseCommand):
    help = 'Cria 50 usuários clientes de teste com dados aleatórios e senha padrão.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('🚀 Iniciando a criação de 50 usuários clientes de teste...'))

        password = 'Senha123456'
        created_count = 0

        for i in range(1, 51): # Loop para criar 50 usuários
            try:
                # Alterna entre pessoa física e jurídica para cobrir ambos os cenários
                is_pessoa_juridica = (i % 2 == 0) # Metade PJ, metade PF

                email = f'cliente_{i}_{fake.uuid4()}@teste.com' # Garante email único
                name = fake.name() if not is_pessoa_juridica else fake.company()
                celular = fake.numerify('###########') # 11 dígitos numéricos

                cpf = None
                cnpj = None

                if is_pessoa_juridica:
                    # Gera um CNPJ que tenta ser único e tem o formato correto
                    cnpj = fake.cnpj()
                    # A validação do modelo pode falhar se o CNPJ gerado for inválido ou duplicado
                    # Para fins de teste, podemos simplificar se a validação for muito rigorosa
                    # Ou garantir que o fake.cnpj() gere um formato que passe na sua regex
                else:
                    # Gera um CPF que tenta ser único e tem o formato correto
                    cpf = fake.cpf()
                    # A validação do modelo pode falhar se o CPF gerado for inválido ou duplicado
                    # Ou garantir que o fake.cpf() gere um formato que passe na sua regex

                # Tenta criar o usuário
                user = User.objects.create_user(
                    email=email,
                    name=name,
                    cnpj=cnpj, # Pode ser None
                    cpf=cpf,   # Pode ser None
                    celular=celular,
                    password=password,
                    is_cliente=True, # Já é o default do create_user, mas explicitamos
                    is_pessoa_juridica=is_pessoa_juridica,
                    is_active=True # Garante que o usuário esteja ativo
                )
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✅ Usuário cliente {user.email} ({user.get_display_name()}) criado com sucesso!'))

            except IntegrityError as e:
                self.stderr.write(self.style.WARNING(f'⚠️ Erro de integridade ao criar usuário {email}: {e}. Tentando próximo...'))
                # Isso pode acontecer se email, CPF ou CNPJ gerados aleatoriamente colidirem
                # Em um ambiente de teste, podemos ignorar e tentar o próximo.
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'❌ Erro inesperado ao criar usuário {email}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'\n🎉 Finalizado! {created_count} usuários clientes de teste criados.'))

