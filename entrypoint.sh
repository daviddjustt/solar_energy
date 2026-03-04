#!/bin/bash

# Interrompe a execução se qualquer comando falhar
set -e

echo "🚀 Iniciando aplicação Solar Energy..."

# ==========================================
# 1. GARANTIR PERMISSÕES DE VOLUME (MEDIA)
# ==========================================
if [ -d "/app/media" ]; then
    echo "📂 Ajustando permissões em /app/media..."
    # 65532 é o ID padrão do usuário non-root em muitas imagens distroless/railway
    chown -R 65532:65532 /app/media || true
    chmod -R 755 /app/media || true
else
    echo "⚠️ Diretório /app/media não encontrado."
fi

# ==========================================
# 2. AGUARDAR BANCO DE DADOS (POSTGRES)
# ==========================================
echo "⏳ Aguardando conexão com o Postgres..."
until psql "$DATABASE_URL" -c '\q' > /dev/null 2>&1; do
  echo "Postgres ainda indisponível - tentando novamente em 3s..."
  sleep 3
done
echo "✅ Conexão estabelecida!"

# ==========================================
# 3. COLETAR ARQUIVOS ESTÁTICOS
# ==========================================
echo "📦 Coletando arquivos estáticos..."
python manage.py collectstatic --noinput --clear

# ==========================================
# 4. EXECUTAR MIGRAÇÕES (CORREÇÃO DO TRAVAMENTO)
# ==========================================
echo "🔄 Verificando e aplicando migrações..."

# O --noinput é CRUCIAL para não travar em perguntas sobre "Stale Content Types"
python manage.py migrate --noinput

echo "✅ Migrações concluídas!"

# ==========================================
# 5. CRIAR SUPERUSER (SE NÃO EXISTIR)
# ==========================================
echo "👤 Verificando Superuser..."
python manage.py shell << EOF
import os
import sys
from django.contrib.auth import get_user_model

User = get_user_model()

email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@solarenergy.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123456')
name = os.environ.get('DJANGO_SUPERUSER_NAME', 'Admin Solar')
cnpj = os.environ.get('DJANGO_SUPERUSER_CNPJ', '00.000.000/0001-00')
cpf = os.environ.get('DJANGO_SUPERUSER_CPF', '000.000.000-00')
celular = os.environ.get('DJANGO_SUPERUSER_CELULAR', '11987654321')

try:
    if not User.objects.filter(email=email).exists():
        print(f"DEBUG: Criando superuser {email}...")
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
        print(f"ℹ️ Superuser {email} já existe.")
except Exception as e:
    print(f"❌ Erro na criação do superuser: {e}")
    # Não interrompemos o boot por erro de superuser já existente/conflito
EOF

# ==========================================
# 6. INICIAR SERVIDOR GUNICORN
# ==========================================
echo "🚀 Iniciando servidor Gunicorn na porta ${PORT:-8080}..."

# Usamos exec para que o Gunicorn se torne o processo principal (PID 1)
exec gunicorn solar.wsgi:application \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers ${GUNICORN_WORKERS:-2} \
    --threads ${GUNICORN_THREADS:-4} \
    --timeout ${GUNICORN_TIMEOUT:-120} \
    --access-logfile - \
    --error-logfile - \
    --log-level ${GUNICORN_LOG_LEVEL:-info}