#!/bin/bash
set -e

# ============================================
# Upload de Backup para Cloudflare R2
# ============================================

ENCRYPTED_FILE=$1
BACKUP_TYPE=$2
TIMESTAMP=$3

# Credenciais Cloudflare R2 (GitHub Secrets)
R2_ENDPOINT="${R2_ENDPOINT}"
R2_BUCKET="${R2_BUCKET}"
R2_ACCESS_KEY="${R2_ACCESS_KEY}"
R2_SECRET_KEY="${R2_SECRET_KEY}"

echo "☁️  Fazendo upload para Cloudflare R2..."

# Upload usando AWS CLI (compatível com R2)
aws s3 cp "${ENCRYPTED_FILE}" \
  "s3://${R2_BUCKET}/backups/${BACKUP_TYPE}/$(basename ${ENCRYPTED_FILE})" \
  --endpoint-url "${R2_ENDPOINT}" \
  --region auto \
  --metadata "backup-type=${BACKUP_TYPE},timestamp=${TIMESTAMP},encrypted=true"

# Upload do hash também
aws s3 cp "${ENCRYPTED_FILE}.sha256" \
  "s3://${R2_BUCKET}/backups/${BACKUP_TYPE}/$(basename ${ENCRYPTED_FILE}).sha256" \
  --endpoint-url "${R2_ENDPOINT}" \
  --region auto

echo "✅ Upload concluído para R2!"
