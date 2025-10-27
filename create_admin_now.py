#!/usr/bin/env python
"""
Script para criar superuser automaticamente com dados fixos
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.config')
os.environ.setdefault('DJANGO_CONFIGURATION', 'Production')

from configurations import importer
importer.install()

django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# ========================================
# 🔐 DADOS DO SUPERUSER (EDITE AQUI)
# ========================================
SUPERUSER_DATA = {
    'email': 'admin@solarenergy.com',
    'name': 'Administrador',
    'cpf': '12345678900',           # 11 dígitos (sem formatação)
    'cnpj': '12345678000190',       # 14 dígitos (sem formatação)
    'celular': '11987654321',       # 11 dígitos
    'password': 'admin123456',      # ⚠️ TROQUE POR UMA SENHA FORTE!
}

# ========================================
# Criar superuser
# ========================================
print('👤 Verificando superuser...')

if User.objects.filter(email=SUPERUSER_DATA['email']).exists():
    print(f"ℹ️  Superuser '{SUPERUSER_DATA['email']}' já existe.")
else:
    try:
        user = User.objects.create_superuser(
            email=SUPERUSER_DATA['email'],
            name=SUPERUSER_DATA['name'],
            cpf=SUPERUSER_DATA['cpf'],
            cnpj=SUPERUSER_DATA['cnpj'],
            celular=SUPERUSER_DATA['celular'],
            password=SUPERUSER_DATA['password']
        )
        
        print('✅ Superuser criado com sucesso!')
        print(f'   Email: {user.email}')
        print(f'   Nome: {user.name}')
        print(f'   CPF: {user.cpf}')
        print(f'   CNPJ: {user.cnpj}')
        print()
        print(f'🌐 Acesse: /admin/')
        print(f'📧 Login: {user.email}')
        print(f'🔑 Senha: {SUPERUSER_DATA["password"]}')
        
    except Exception as e:
        print(f'❌ Erro ao criar superuser: {e}')
        # Não faz exit(1) para não impedir o Gunicorn de subir
