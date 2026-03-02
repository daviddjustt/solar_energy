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
