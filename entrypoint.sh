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

# ==========================================
# 3. APLICAR MIGRAÇÕES
# ==========================================
echo "🔄 Aplicando migrações..."
python manage.py migrate --noinput

echo ""

# ==========================================
# 4. CRIAR SUPERUSER (SE NÃO EXISTIR)
# ==========================================
echo "👤 Criando superuser..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()

email = "${DJANGO_SUPERUSER_EMAIL:-admin@solarenergy.com}"
password = "${DJANGO_SUPERUSER_PASSWORD:-admin123456}"

if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(
        email=email,
        password=password,
        name="Admin"
    )
    print(f"✅ Superuser {email} criado com sucesso!")
else:
    print(f"ℹ️  Superuser {email} já existe")
EOF

echo ""

# ==========================================
# 5. INICIAR SERVIDOR GUNICORN
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
