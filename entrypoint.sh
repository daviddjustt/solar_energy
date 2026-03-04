#!/bin/bash
set -e

echo "🚀 Iniciando aplicação Solar Energy..."
echo ""

# ==========================================
# 1. GARANTIR PERMISSÕES DO VOLUME
# =========================================="

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


echo "✅ Banco detectado! Prosseguindo..."
echo ""

echo "⏳ Aguardando banco de dados..."
# Usamos a DATABASE_URL diretamente para o teste de conexão
until psql "$DATABASE_URL" -c '\q'; do
  echo "Postgres ainda indisponível ou senha incorreta - tentando novamente..."
  sleep 5
done
echo "✅ Conexão estabelecida!"

# ==========================================
# 2. COLETAR ARQUIVOS ESTÁTICOS
# ==========================================
echo "📦 Coletando arquivos estáticos..."
python manage.py collectstatic --noinput --clear

echo "🔄 Verificando e aplicando migrações..."

echo "🔄 Recriando esquema de banco de dados..."

# Apaga todo o conteúdo e recria a estrutura
python manage.py flush --no-input

# Garante que novas migrações baseadas no models.py limpo sejam criadas
python manage.py makemigrations documents users

# Aplica as novas migrações limpas
python manage.py migrate --noinput

echo "✅ Migrações concluídas!"

# ==========================================
# 4. CRIAR SUPERUSER (SE NÃO EXISTIR)
# ==========================================
echo "👤 Criando superuser..."
python manage.py shell << EOF
import os
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
import sys # Importar sys para sys.exit()

User = get_user_model()

# Obter valores das variáveis de ambiente ou usar defaults seguros
# Certifique-se de definir estas variáveis no Railway (ou no seu ambiente local)
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@solarenergy.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123456')
name = os.environ.get('DJANGO_SUPERUSER_NAME', 'Admin Solar')
cnpj = os.environ.get('DJANGO_SUPERUSER_CNPJ', '00.000.000/0001-00') # Exemplo de CNPJ válido e formatado
cpf = os.environ.get('DJANGO_SUPERUSER_CPF', '000.000.000-00')     # Exemplo de CPF válido e formatado
celular = os.environ.get('DJANGO_SUPERUSER_CELULAR', '11987654321') # Exemplo de celular válido (11 dígitos)

try:
    # Tenta encontrar o usuário pelo email, que é o USERNAME_FIELD
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
    # Se a criação do superusuário falhar, o deploy deve falhar
    sys.exit(1)
EOF
echo ""
# ==========================================
# 5. CRIAR USUÁRIOS CLIENTES DE TESTE
# ==========================================
echo "👥 Criando usuários clientes de teste..."
# python manage.py create_test_clients # ✅ Nova linha aqui!
echo ""

# ==========================================
# 6. INICIAR SERVIDOR GUNICORN
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
