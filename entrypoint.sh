#!/bin/bash
set -e

echo "🚀 Iniciando aplicação Solar Energy..."
echo ""

# ==========================================
# 1. GARANTIR PERMISSÕES DO VOLUME
# ==========================================
echo "🔐 Configurando permissões do volume /app/media..."

# Se o diretório /app/media existe (volume montado)
if [ -d "/app/media" ]; then
    # Dar permissões ao usuário nonroot (UID 65532)
    # Executar como root (o entrypoint começa como root)
    chown -R 65532:65532 /app/media
    chmod -R 755 /app/media
    echo "✅ Permissões configuradas para /app/media"
else
    echo "⚠️  Diretório /app/media não encontrado (volume não montado?)"
fi

# ==========================================
# 2. COLETAR ARQUIVOS ESTÁTICOS
# ==========================================
echo "📦 Coletando arquivos estáticos..."
python manage.py collectstatic --noinput --clear

echo ""
# Define o nome da migração problemática e o app
PROBLEM_MIGRATION="none"
APP_LABEL="documents"
PREVIOUS_MIGRATION="0001_initial" # A migração que deveria vir antes da problemática

# Verifica se a migração problemática está registrada como aplicada no DB
# E se o arquivo correspondente NÃO existe localmente no container.
# Isso é um hack para lidar com migrações "fantasmas" em ambientes remotos.
if python manage.py showmigrations "$APP_LABEL" | grep -q "$PROBLEM_MIGRATION [X]"; then
    if [ ! -f "/code/solar/$APP_LABEL/migrations/$PROBLEM_MIGRATION.py" ]; then
        echo "⚠️ Detectada migração problemática '$PROBLEM_MIGRATION' no DB do Railway, mas o arquivo não existe localmente."
        echo "   Marcando a migração '$PROBLEM_MIGRATION' como 'não aplicada' no histórico do DB para resolver a inconsistência."
        # Este comando marca a migração problemática (e quaisquer outras após ela para este app)
        # como não aplicadas no banco de dados, ao "fingir" que a migração anterior é a última aplicada.
        python manage.py migrate --fake "$APP_LABEL" "$PREVIOUS_MIGRATION"
        echo "✅ Migração '$PROBLEM_MIGRATION' marcada como não aplicada no DB."
    fi
fi

# Agora, execute makemigrations e migrate normalmente
#echo "Executando python manage.py makemigrations --noinput..."
#python manage.py makemigrations --noinput
#echo ""

echo "Executando python manage.py migrate --noinput..."
python manage.py migrate --noinput
echo ""

# ==========================================
# 4. CRIAR SUPERUSER E USUÁRIOS DE TESTE
# ==========================================
echo "👤 Configurando usuários (superuser e de teste)..." # Título mais abrangente
python manage.py shell << EOF
import os
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
import sys
import random
import string
from django.contrib.auth.models import Group

User = get_user_model()

# Obter valores das variáveis de ambiente ou usar defaults seguros
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@solarenergy.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123456')
name = os.environ.get('DJANGO_SUPERUSER_NAME', 'Admin Solar')
cnpj = os.environ.get('DJANGO_SUPERUSER_CNPJ', '00.000.000/0001-00')
cpf = os.environ.get('DJANGO_SUPERUSER_CPF', '000.000.000-00')
celular = os.environ.get('DJANGO_SUPERUSER_CELULAR', '11987654321')

try:
    if not User.objects.filter(email=email).exists():
        print(f"Attempting to create superuser {email}...")
        User.objects.create_superuser(
            email=email,
            password=password,
            name=name,
            cnpj=cnpj,
            cpf=cpf,
            celular=celular
        )
        print(f"✅ Superuser {email} criado com sucesso!")
    else:
        print(f"ℹ️  Superuser {email} já existe, pulando criação.")
except Exception as e:
    print(f"❌ Erro crítico ao criar superuser: {e}", file=sys.stderr)
    sys.exit(1)

# ==========================================
# 5. CRIAR GRUPOS (SE NÃO EXISTIREM)
# ==========================================
print("\n👥 Verificando e criando grupos...")
groups_to_create = ['admins', 'tecnicos', 'clientes', 'clientes_pf', 'clientes_pj']
for group_name in groups_to_create:
    group, created = Group.objects.get_or_create(name=group_name)
    if created:
        print(f"✅ Grupo '{group_name}' criado.")
    else:
        print(f"ℹ️  Grupo '{group_name}' já existe.")

# ==========================================
# 6. CRIAR USUÁRIOS DE TESTE (2 admins, 2 técnicos, 6 padrão)
# ==========================================
print("\n➕ Criando usuários de teste...")

def generate_random_string(length=10):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

# Lista para armazenar as credenciais geradas
generated_credentials = []

# Criar 2 usuários Admin
for i in range(1, 3):
    user_email = f"admin_test_{i}@solarenergy.com"
    user_password = generate_random_string(12)
    user_name = f"Admin Test {i}"
    user_celular = f"119{random.randint(10000000, 99999999)}" # Celular aleatório

    if not User.objects.filter(email=user_email).exists():
        try:
            user = User.objects.create_user(
                email=user_email,
                password=user_password,
                name=user_name,
                is_admin=True, # Definir como admin
                celular=user_celular,
                # Outros campos necessários para o seu CustomUser
                cpf=f"{random.randint(100, 999)}.{random.randint(100, 999)}.{random.randint(100, 999)}-{random.randint(10, 99)}",
                cnpj=f"{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}/{random.randint(1000, 9999)}-{random.randint(10, 99)}",
            )
            # Adicionar ao grupo 'admins'
            Group.objects.get(name='admins').user_set.add(user)
            generated_credentials.append({'role': 'Admin', 'email': user_email, 'password': user_password})
            print(f"✅ Usuário Admin '{user_email}' criado.")
        except Exception as e:
            print(f"❌ Erro ao criar usuário Admin {user_email}: {e}", file=sys.stderr)
    else:
        print(f"ℹ️  Usuário Admin '{user_email}' já existe.")

# Criar 2 usuários Técnicos
for i in range(1, 3):
    user_email = f"tecnico_test_{i}@solarenergy.com"
    user_password = generate_random_string(12)
    user_name = f"Tecnico Test {i}"
    user_celular = f"119{random.randint(10000000, 99999999)}"

    if not User.objects.filter(email=user_email).exists():
        try:
            user = User.objects.create_user(
                email=user_email,
                password=user_password,
                name=user_name,
                is_tecnico=True, # Definir como técnico
                celular=user_celular,
                cpf=f"{random.randint(100, 999)}.{random.randint(100, 999)}.{random.randint(100, 999)}-{random.randint(10, 99)}",
                cnpj=f"{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}/{random.randint(1000, 9999)}-{random.randint(10, 99)}",
            )
            # Adicionar ao grupo 'tecnicos'
            Group.objects.get(name='tecnicos').user_set.add(user)
            generated_credentials.append({'role': 'Técnico', 'email': user_email, 'password': user_password})
            print(f"✅ Usuário Técnico '{user_email}' criado.")
        except Exception as e:
            print(f"❌ Erro ao criar usuário Técnico {user_email}: {e}", file=sys.stderr)
    else:
        print(f"ℹ️  Usuário Técnico '{user_email}' já existe.")

# Criar 6 usuários Padrão (Clientes)
for i in range(1, 7):
    user_email = f"cliente_test_{i}@solarenergy.com"
    user_password = generate_random_string(12)
    user_name = f"Cliente Test {i}"
    user_celular = f"119{random.randint(10000000, 99999999)}"
    is_pj = (i % 2 == 0) # Alternar entre PF e PJ

    if not User.objects.filter(email=user_email).exists():
        try:
            user = User.objects.create_user(
                email=user_email,
                password=user_password,
                name=user_name,
                is_cliente=True, # Definir como cliente
                is_pessoa_juridica=is_pj, # Alternar PF/PJ
                celular=user_celular,
                cpf=f"{random.randint(100, 999)}.{random.randint(100, 999)}.{random.randint(100, 999)}-{random.randint(10, 99)}" if not is_pj else None,
                cnpj=f"{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}/{random.randint(1000, 9999)}-{random.randint(10, 99)}" if is_pj else None,
            )
            # Adicionar ao grupo 'clientes' e ao subgrupo específico
            Group.objects.get(name='clientes').user_set.add(user)
            if is_pj:
                Group.objects.get(name='clientes_pj').user_set.add(user)
            else:
                Group.objects.get(name='clientes_pf').user_set.add(user)

            generated_credentials.append({'role': 'Cliente', 'type': 'PJ' if is_pj else 'PF', 'email': user_email, 'password': user_password})
            print(f"✅ Usuário Cliente '{user_email}' (PJ={is_pj}) criado.")
        except Exception as e:
            print(f"❌ Erro ao criar usuário Cliente {user_email}: {e}", file=sys.stderr)
    else:
        print(f"ℹ️  Usuário Cliente '{user_email}' já existe.")

print("\n📋 Credenciais dos usuários de teste criados:")
for cred in generated_credentials:
    print(f"  - Função: {cred['role']}{f' ({cred.get('type', '')})' if cred.get('type') else ''}, Email: {cred['email']}, Senha: {cred['password']}")

EOF # ✅ O marcador EOF final está aqui, fechando o bloco python manage.py shell

# ==========================================
# 7. INICIAR SERVIDOR GUNICORN
# ==========================================
echo "✅ Iniciando servidor Gunicorn..."
exec gunicorn solar.wsgi:application \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers ${GUNICORN_WORKERS:-2} \
    --threads ${GUNICORN_THREADS:-4} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    --error-logfile - \
    --log-level ${GUNICORN_LOG_LEVEL:-info}
