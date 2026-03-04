#!/bin/bash
set -e

echo "🚀 Iniciando Solar Energy às $(date)"

# 1. Ajuste de Permissões (Volume montado pelo Railway)
if [ -d "/app/media" ]; then
    chown -R 65532:65532 /app/media || true
    chmod -R 755 /app/media || true
fi

# 2. Espera pelo Banco
echo "⏳ Aguardando Postgres..."
until psql "$DATABASE_URL" -c '\q' > /dev/null 2>&1; do
  echo "Postgres ainda offline - tentando novamente..."
  sleep 3
done

# 4. SINCRONIZAÇÃO AUTOMÁTICA (Resolve o aviso do Log)
echo "🔄 Gerando migrações automáticas para sincronizar models.py..."
# Forçamos a criação para evitar o aviso "models have changes not reflected"
python manage.py makemigrations documents --noinput
python manage.py makemigrations users --noinput
python manage.py makemigrations files --noinput

echo "🔄 Aplicando migrações..."
python manage.py migrate --noinput
echo "✅ Banco de dados atualizado com sucesso!"

# 5. Verificação de Superuser (Script inline rápido)
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
        name='Admin Solar',
        cnpj='00.000.000/0001-00',
        cpf='000.000.000-00',
        celular='11987654321'
    )
    print(f"✅ Superuser {email} criado!")
else:
    print(f"ℹ️ Superuser {email} já existe.")
EOF

# 6. Execução do Gunicorn
echo "✅ Tudo pronto! Iniciando Gunicorn..."
exec gunicorn solar.wsgi:application \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -