#!/bin/bash

# Source de configuración
source "$BACKUP_BASE/infra/backup.conf"

set -e
DATE=$(date +%F)
mkdir -p "$BACKUP_DIR"

echo "=== Iniciando backup $(date +%Y-%m-%d\ %H:%M:%S) ===" | tee -a "$LOG_FILE"

cd "$DOCKER_COMPOSE_DIR"

# Paso 1: Dump de PostgreSQL
echo "1. Haciendo dump de BD..." | tee -a "$LOG_FILE"
docker compose exec -T db pg_dump -U "$BACKUP_DB_USER" "$BACKUP_DB_NAME" | gzip > "$BACKUP_DIR/db_${DATE}.sql.gz"
echo "   ✓ Guardado: $BACKUP_DIR/db_${DATE}.sql.gz" | tee -a "$LOG_FILE"

# Paso 1b: VERIFICAR dump (Nivel 1)
echo "2b. Verificando integridad de BD..." | tee -a "$LOG_FILE"
if gunzip -t "$BACKUP_DIR/db_${DATE}.sql.gz"; then
    echo "   ✓ Dump OK" | tee -a "$LOG_FILE"
else
    echo "   ✗ ERROR: Dump corrupto" | tee -a "$LOG_FILE"
    exit 1
fi

# Paso 2: Comprimir filestore
echo "2. Comprimiendo filestore..." | tee -a "$LOG_FILE"
docker compose exec -T odoo tar -czf - /var/lib/odoo/filestore > "$BACKUP_DIR/filestore_${DATE}.tar.gz"
echo "   ✓ Guardado: $BACKUP_DIR/filestore_${DATE}.tar.gz" | tee -a "$LOG_FILE"

# Paso 2b: VERIFICAR filestore (Nivel 1)
echo "3b. Verificando integridad de filestore..." | tee -a "$LOG_FILE"
if tar -tzf "$BACKUP_DIR/filestore_${DATE}.tar.gz" > /dev/null; then
    echo "   ✓ Filestore OK" | tee -a "$LOG_FILE"
else
    echo "   ✗ ERROR: Filestore corrupto" | tee -a "$LOG_FILE"
    exit 1
fi

echo "=== Backup completado exitosamente ===" | tee -a "$LOG_FILE"
echo "Archivos generados:" | tee -a "$LOG_FILE"
ls -lh "$BACKUP_DIR/db_${DATE}.sql.gz" "$BACKUP_DIR/filestore_${DATE}.tar.gz" | tee -a "$LOG_FILE"
