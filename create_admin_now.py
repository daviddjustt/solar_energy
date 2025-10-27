#!/usr/bin/env python
import os
import sys

# Adicionar o projeto ao path
sys.path.insert(0, os.path.dirname(__file__))

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar.config')
os.environ.setdefault('DJANGO_CONFIGURATION', 'Production')

from configurations import importer
importer.install()

import django
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Criar superuser
username = input("Username: ")
email = input("Email: ")
password = input("Password: ")

if User.objects.filter(username=username).exists():
    print(f"⚠️  User '{username}' já existe!")
else:
    User.objects.create_superuser(username, email, password)
    print(f"✅ Superuser '{username}' criado com sucesso!")
