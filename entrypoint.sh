#!/bin/bash
set -e

echo "🚀 Iniciando aplicação Solar Energy..."

# ==========================================
# 1. PERMISSÕES DE VOLUME
# ==========================================
if [ -d "/app/media" ]; then
    chown -R 65532:65532 /app/media || true
    chmod -R 755 /app/media || true
    echo "✅ Permissões de mídia configuradas."
fi

# ==========================================
# 2. CONEXÃO COM O BANCO
# ==========================================
echo "⏳ Aguardando Postgres em $DATABASE_URL..."
until psql "$DATABASE_URL" -c '\q' > /dev/null 2>&1; do
  echo "Banco ainda indisponível - tentando novamente..."
  sleep 3
done
echo "✅ Conexão estabelecida!"

# ==========================================
# 3. STATIC FILES
# ==========================================
echo "📦 Coletando arquivos estáticos..."
python manage.py collectstatic --noinput --clear

# ==========================================
# 4. SINCRONIZAÇÃO DE MIGRAÇÕES (CRUCIAL)
# ==========================================
echo "🔄 Gerando migrações faltantes..."
# Isso resolve o aviso "Your models have changes not reflected in migrations"
python manage.py makemigrations users --noinput
python manage.py makemigrations documents --noinput
python manage.py makemigrations --noinput

echo "🔄 Aplicando migrações no banco..."
# O --noinput evita o travamento de 10 minutos por perguntas do Django
python manage.py migrate --noinput

echo "✅ Migrações concluídas!"

# ==========================================
# 5. SUPERUSER
# ==========================================
echo "👤 Verificando Superuser..."
python manage.py shell << EOF
import os
from django.contrib.auth import get_user_model
User = get_user_model()
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@solarenergy.com')
if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(
        email=email,
        password=os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123456'),
        name=os.environ.get('DJANGO_SUPERUSER_NAME', 'Admin Solar'),
        cnpj=os.environ.get('DJANGO_SUPERUSER_CNPJ', '00.000.000/0001-00'),
        cpf=os.environ.get('DJANGO_SUPERUSER_CPF', '000.000.000-00'),
        celular=os.environ.get('DJANGO_SUPERUSER_CELULAR', '11987654321')
    )
    print(f"✅ Superuser {email} criado!")
else:
    print(f"ℹ️ Superuser {email} já existe.")
EOF

# ==========================================
# 6. START SERVER
# ==========================================
echo "🚀 Iniciando Gunicorn..."
exec gunicorn solar.wsgi:application \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -