#!/bin/bash
set -e

# ============================================
# Script de Backup PostgreSQL - Conforme LGPD
# ============================================

# Variáveis de ambiente (configurar no GitHub Secrets)
RAILWAY_TOKEN="${RAILWAY_TOKEN}"
DATABASE_URL="${DATABASE_URL}"
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY}"
BACKUP_TYPE="${BACKUP_TYPE:-daily}"  # daily, weekly, monthly

# Configurações
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/tmp/backups"
BACKUP_FILE="solar_energy_${BACKUP_TYPE}_${TIMESTAMP}.sql"
ENCRYPTED_FILE="${BACKUP_FILE}.enc"

# Criar diretório de backup
mkdir -p "${BACKUP_DIR}"

echo "🔄 Iniciando backup ${BACKUP_TYPE}..."
echo "📅 Data/Hora: $(date)"

# ============================================
# 1. DUMP DO BANCO DE DADOS
# ============================================
echo "📦 Criando dump do PostgreSQL..."

# Usando Railway CLI para acessar o banco
railway run pg_dump "${DATABASE_URL}" \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-privileges \
  > "${BACKUP_DIR}/${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
echo "✅ Dump criado: ${BACKUP_FILE} (${BACKUP_SIZE})"

# ============================================
# 2. CRIPTOGRAFIA AES-256 (LGPD)
# ============================================
echo "🔐 Criptografando backup com AES-256..."

openssl enc -aes-256-cbc \
  -salt \
  -pbkdf2 \
  -in "${BACKUP_DIR}/${BACKUP_FILE}" \
  -out "${BACKUP_DIR}/${ENCRYPTED_FILE}" \
  -pass pass:"${ENCRYPTION_KEY}"

ENCRYPTED_SIZE=$(du -h "${BACKUP_DIR}/${ENCRYPTED_FILE}" | cut -f1)
echo "✅ Backup criptografado: ${ENCRYPTED_FILE} (${ENCRYPTED_SIZE})"

# Remover arquivo não criptografado (segurança)
rm -f "${BACKUP_DIR}/${BACKUP_FILE}"

# ============================================
# 3. HASH PARA INTEGRIDADE
# ============================================
echo "🔏 Gerando hash SHA-256 para integridade..."

sha256sum "${BACKUP_DIR}/${ENCRYPTED_FILE}" > "${BACKUP_DIR}/${ENCRYPTED_FILE}.sha256"
HASH=$(cat "${BACKUP_DIR}/${ENCRYPTED_FILE}.sha256" | cut -d' ' -f1)
echo "✅ Hash: ${HASH}"

# ============================================
# 4. UPLOAD PARA CLOUDFLARE R2
# ============================================
echo "☁️  Fazendo upload para Cloudflare R2..."

./scripts/upload_backup.sh \
  "${BACKUP_DIR}/${ENCRYPTED_FILE}" \
  "${BACKUP_TYPE}" \
  "${TIMESTAMP}"

echo "✅ Upload concluído!"

# ============================================
# 5. LIMPEZA LOCAL
# ============================================
echo "🧹 Limpando arquivos temporários..."
rm -rf "${BACKUP_DIR}"

# ============================================
# 6. APLICAR POLÍTICA DE RETENÇÃO LGPD
# ============================================
echo "📋 Aplicando política de retenção LGPD..."
./scripts/cleanup_old_backups.sh "${BACKUP_TYPE}"

echo "🎉 Backup ${BACKUP_TYPE} concluído com sucesso!"
echo "📊 Resumo:"
echo "   - Tipo: ${BACKUP_TYPE}"
echo "   - Arquivo: ${ENCRYPTED_FILE}"
echo "   - Tamanho: ${ENCRYPTED_SIZE}"
echo "   - Hash: ${HASH}"
echo "   - Data: $(date)"
