#!/bin/bash
set -e

# ============================================
# Limpeza de Backups Antigos - Conforme LGPD
# ============================================

BACKUP_TYPE=$1

# Política de retenção LGPD
case "${BACKUP_TYPE}" in
  daily)
    RETENTION_DAYS=7
    ;;
  weekly)
    RETENTION_DAYS=30
    ;;
  monthly)
    RETENTION_DAYS=365
    ;;
  *)
    echo "❌ Tipo de backup inválido: ${BACKUP_TYPE}"
    exit 1
    ;;
esac

echo "🗑️  Removendo backups ${BACKUP_TYPE} com mais de ${RETENTION_DAYS} dias..."

# Calcular data limite
CUTOFF_DATE=$(date -d "${RETENTION_DAYS} days ago" +%Y%m%d)

# Listar e remover backups antigos
aws s3 ls "s3://${R2_BUCKET}/backups/${BACKUP_TYPE}/" \
  --endpoint-url "${R2_ENDPOINT}" \
  --region auto | while read -r line; do
    
    BACKUP_DATE=$(echo $line | awk '{print $4}' | grep -oP '\d{8}' | head -1)
    BACKUP_FILE=$(echo $line | awk '{print $4}')
    
    if [[ "${BACKUP_DATE}" -lt "${CUTOFF_DATE}" ]]; then
      echo "🗑️  Removendo: ${BACKUP_FILE} (${BACKUP_DATE} < ${CUTOFF_DATE})"
      
      aws s3 rm "s3://${R2_BUCKET}/backups/${BACKUP_TYPE}/${BACKUP_FILE}" \
        --endpoint-url "${R2_ENDPOINT}" \
        --region auto
        
      # Remover hash também
      aws s3 rm "s3://${R2_BUCKET}/backups/${BACKUP_TYPE}/${BACKUP_FILE}.sha256" \
        --endpoint-url "${R2_ENDPOINT}" \
        --region auto 2>/dev/null || true
    fi
done

echo "✅ Limpeza concluída! Backups retidos: ${RETENTION_DAYS} dias"
