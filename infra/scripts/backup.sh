#!/bin/bash
set -euo pipefail

# Source de configuración
source "${BACKUP_BASE:?BACKUP_BASE no está definida}/infra/backup.conf"

# Validar variables críticas (se usan en rm -rf)
: "${BACKUPS_DIR:?BACKUPS_DIR no está definida en backup.conf}"
: "${DOCKER_COMPOSE_DIR:?DOCKER_COMPOSE_DIR no está definida en backup.conf}"
: "${LOG_FILE:?LOG_FILE no está definida en backup.conf}"

BACKUP_NAME="backup_$(date +%F_%H-%M-%S)"
BACKUP_DIR="$BACKUPS_DIR/$BACKUP_NAME"
ARCHIVE="$BACKUPS_DIR/$BACKUP_NAME.tar.gz"

mkdir -p "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

log() { echo "$1" | tee -a "$LOG_FILE"; }

log "=== Iniciando backup $(date '+%Y-%m-%d %H:%M:%S') ==="

cd "$DOCKER_COMPOSE_DIR"

# Paso 1: Dump de PostgreSQL (sin pipe: si pg_dump falla, set -e aborta)
log "1. Haciendo dump de BD..."
docker compose exec -T db pg_dump -U "$BACKUP_DB_USER" "$BACKUP_DB_NAME" > "$BACKUP_DIR/db.sql"
log "   ✓ Guardado: $BACKUP_DIR/db.sql"

# Paso 2: Copiar filestore desde el contenedor
# (no crear $BACKUP_DIR/filestore antes: si existe, cp lo anida como filestore/filestore)
log "2. Copiando filestore..."
docker compose cp odoo:/var/lib/odoo/filestore "$BACKUP_DIR/filestore"
log "   ✓ Guardado: $BACKUP_DIR/filestore"

# Paso 3: Comprimir la carpeta completa en un solo archivo
log "3. Comprimiendo backup..."
tar -C "$BACKUPS_DIR" -czf "$ARCHIVE" "$BACKUP_NAME"
log "   ✓ Guardado: $ARCHIVE"

# Paso 4: Verificar integridad del archivo final y generar checksum
log "4. Verificando integridad..."
if tar -tzf "$ARCHIVE" > /dev/null; then
    log "   ✓ Archivo OK"
else
    log "   ✗ ERROR: Archivo corrupto"
    exit 1
fi
(cd "$BACKUPS_DIR" && sha256sum "$BACKUP_NAME.tar.gz" > "$BACKUP_NAME.tar.gz.sha256")
log "   ✓ Checksum generado"

# Paso 5: Eliminar la carpeta sin comprimir
rm -rf "$BACKUP_DIR"

log "=== Backup completado exitosamente ==="
log "Archivo generado:"
ls -lh "$ARCHIVE" | tee -a "$LOG_FILE"