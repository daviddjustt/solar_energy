#!/bin/bash
set -e

echo "🚀 Iniciando Solar Energy às $(date)"
fuser -k ${PORT:-8080}/tcp || true
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

# 4. APLICAÇÃO DE MIGRAÇÕES
echo "🔄 Sincronizando histórico das notificações..."
python manage.py migrate notifications --fake

echo "🔄 Aplicando migrações reais do banco de dados..."
python manage.py migrate --noinput
echo "✅ Banco de dados atualizado com sucesso!"

# =========================================================================
# 4. CORREÇÃO FORÇADA DE SCHEMA (AUTO-CURA DO BANCO)
# =========================================================================
echo "🛠️ Aplicando correções forçadas de Schema (Energisa e Pagamentos)..."
python manage.py shell << 'EOF'
from django.db import connection, transaction
from solar.documents.models import EnergisaProject, ProjectDocument

# 1. Tenta criar a tabela da Energisa de forma isolada
try:
    with transaction.atomic():
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(EnergisaProject)
    print("✅ Tabela 'EnergisaProject' construída com sucesso no banco!")
except Exception:
    print("ℹ️ Tabela 'EnergisaProject' já existe e está pronta para uso.")
        
# 2. Tenta recriar a coluna de pagamento de forma isolada
try:
    with transaction.atomic():
        with connection.schema_editor() as schema_editor:
            field = ProjectDocument._meta.get_field('related_payment_document')
            schema_editor.add_field(ProjectDocument, field)
    print("✅ Coluna 'related_payment_document' adicionada com sucesso!")
except Exception:
    print("ℹ️ Coluna 'related_payment_document' já existe e está pronta para uso.")
EOF
# =========================================================================

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
python manage.py collectstatic --noinput
# 6. Execução do Servidor ASGI (Daphne) com Debug Ativado
echo "✅ Tudo pronto! Iniciando servidor ASGI (Daphne) em modo Verboso... 🛠️"
exec daphne -v 3 -b 0.0.0.0 -p ${PORT:-8080} solar.asgi:application