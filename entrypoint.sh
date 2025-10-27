#!/bin/bash
set -e

echo "🚀 Iniciando aplicação Solar Energy..."
echo ""

# Rodar migrações
echo "🔄 Aplicando migrações..."
python manage.py migrate --noinput
echo ""

# Criar superuser via management command
echo "👤 Criando superuser..."
python manage.py create_initial_superuser
echo ""

# Iniciar Gunicorn
echo "✅ Iniciando servidor Gunicorn..."
exec python -m newrelic.admin run-program gunicorn \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-2} \
    --access-logfile - \
    --error-logfile - \
    solar.wsgi:application
