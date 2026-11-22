#!/bin/bash
set -euo pipefail

# Códigos de salida: 0 = todo bien (o nube deshabilitada), 1 = falló algo local,
# 2 = backup local OK pero falló la parte de la nube.

# Source de configuración
source "${BACKUP_BASE:?BACKUP_BASE no está definida}/infra/backup.conf"

# Validar variables críticas (se usan en rm -rf y en la retención)
: "${BACKUPS_DIR:?BACKUPS_DIR no está definida en backup.conf}"
: "${DOCKER_COMPOSE_DIR:?DOCKER_COMPOSE_DIR no está definida en backup.conf}"
: "${LOG_FILE:?LOG_FILE no está definida en backup.conf}"
: "${RETENTION_DIARIO:?RETENTION_DIARIO no está definida en backup.conf}"
: "${RETENTION_SEMANAL:?RETENTION_SEMANAL no está definida en backup.conf}"
: "${CLOUD_BACKUP:?CLOUD_BACKUP no está definida en backup.conf}"

if [[ "$BACKUPS_DIR" != /* ]]; then
    echo "ERROR: BACKUPS_DIR debe ser una ruta absoluta (valor actual: $BACKUPS_DIR)" >&2
    exit 1
fi
for n in "$RETENTION_DIARIO" "$RETENTION_SEMANAL"; do
    if [[ ! "$n" =~ ^[1-9][0-9]*$ ]]; then
        echo "ERROR: RETENTION_* debe ser un entero >= 1 (valor actual: $n)" >&2
        exit 1
    fi
done
if [[ "$CLOUD_BACKUP" != "true" && "$CLOUD_BACKUP" != "false" ]]; then
    echo "ERROR: CLOUD_BACKUP debe ser 'true' o 'false' (valor actual: $CLOUD_BACKUP)" >&2
    exit 1
fi
# R2_REMOTE y RCLONE_CONFIG se validan dentro de upload_to_r2: un problema con
# la nube no debe impedir los backups locales.

# Fecha y día de la semana se fijan al inicio: si el script termina pasada
# la medianoche, el tipo de backup (diario/semanal) no cambia.
NOW="$(date +%F_%H-%M-%S)"
DAY_OF_WEEK="$(date +%u)"   # 7 = domingo

BACKUP_NAME="backup_$NOW"
BACKUP_DIR="$BACKUPS_DIR/$BACKUP_NAME"    # carpeta temporal sin comprimir
DAILY_DIR="$BACKUPS_DIR/daily"
WEEKLY_DIR="$BACKUPS_DIR/weekly"
ARCHIVE="$DAILY_DIR/$BACKUP_NAME.tar.gz"
ARCHIVE_TMP="$ARCHIVE.tmp"               # el nombre final solo existe si el archivo está verificado

mkdir -p "$BACKUP_DIR" "$DAILY_DIR" "$WEEKLY_DIR" "$(dirname "$LOG_FILE")"

# Si algo falla, no dejar carpeta ni archivo parcial
trap 'rm -rf "$BACKUP_DIR" "$ARCHIVE_TMP"' EXIT

log() { echo "$1" | tee -a "$LOG_FILE"; }

# Conserva los $2 backups más recientes de un directorio local y elimina el resto.
# Los nombres con fecha ISO ordenan cronológicamente.
prune_local() {
    local dir="$1" keep="$2" f excess
    local -a files
    mapfile -t files < <(find "$dir" -maxdepth 1 -name 'backup_*.tar.gz' -printf '%f\n' | sort)
    excess=$(( ${#files[@]} - keep ))
    (( excess > 0 )) || return 0
    for f in "${files[@]:0:excess}"; do
        rm -f "$dir/$f" "$dir/$f.sha256"
        log "   - Eliminado (local): $(basename "$dir")/$f"
    done
}

# Subida a R2. Cada comando lleva "|| return 1": esta función se llama dentro de
# un "if", donde set -e no aplica, y un fallo intermedio quedaría oculto.
upload_to_r2() {
    [[ -n "${R2_REMOTE:-}" ]]     || { log "   [ERROR] R2_REMOTE no está definida en backup.conf"; return 1; }
    [[ -f "${RCLONE_CONFIG:-}" ]] || { log "   [ERROR] No existe el archivo de configuración de rclone: ${RCLONE_CONFIG:-<sin definir>}"; return 1; }
    command -v rclone > /dev/null || { log "   [ERROR] rclone no está instalado"; return 1; }

    rclone copyto "$ARCHIVE"        "$R2_REMOTE/daily/$BACKUP_NAME.tar.gz"        || return 1
    rclone copyto "$ARCHIVE.sha256" "$R2_REMOTE/daily/$BACKUP_NAME.tar.gz.sha256" || return 1
    if [[ "$DAY_OF_WEEK" -eq 7 ]]; then
        rclone copyto "$ARCHIVE"        "$R2_REMOTE/weekly/$BACKUP_NAME.tar.gz"        || return 1
        rclone copyto "$ARCHIVE.sha256" "$R2_REMOTE/weekly/$BACKUP_NAME.tar.gz.sha256" || return 1
    fi
}

# Igual que prune_local, pero sobre un prefijo del bucket de R2
prune_remote() {
    local path="$1" keep="$2" f excess listing
    local -a files
    listing="$(rclone lsf "$R2_REMOTE/$path" --files-only)" || return 1
    mapfile -t files < <(printf '%s\n' "$listing" | grep -E '^backup_.*\.tar\.gz$' | sort || true)
    excess=$(( ${#files[@]} - keep ))
    (( excess > 0 )) || return 0
    for f in "${files[@]:0:excess}"; do
        rclone deletefile "$R2_REMOTE/$path/$f" || return 1
        rclone deletefile "$R2_REMOTE/$path/$f.sha256" || log "   ! No se pudo eliminar $path/$f.sha256 (¿ya no existía?)"
        log "   - Eliminado (R2): $path/$f"
    done
}

if [[ "$DAY_OF_WEEK" -eq 7 ]]; then TIPO="diario + semanal"; else TIPO="diario"; fi
log "=== Iniciando backup ($TIPO) $(date '+%Y-%m-%d %H:%M:%S') ==="

cd "$DOCKER_COMPOSE_DIR"

# Paso 1: Dump de PostgreSQL (sin pipe: si pg_dump falla, set -e aborta)
log "1. Haciendo dump de BD..."
docker compose exec -T db pg_dump -U "$BACKUP_DB_USER" "$BACKUP_DB_NAME" > "$BACKUP_DIR/db.sql"
log "   [OK] Guardado: $BACKUP_DIR/db.sql"

# Paso 2: Copiar filestore desde el contenedor (sin detener Odoo)
# (no crear $BACKUP_DIR/filestore antes: si existe, cp lo anida como filestore/filestore)
log "2. Copiando filestore..."
docker compose cp odoo:/var/lib/odoo/filestore "$BACKUP_DIR/filestore"
log "   [OK] Guardado: $BACKUP_DIR/filestore"

# Paso 3: Comprimir, verificar y generar checksum
log "3. Comprimiendo y verificando..."
tar -C "$BACKUPS_DIR" -czf "$ARCHIVE_TMP" "$BACKUP_NAME"
if tar -tzf "$ARCHIVE_TMP" > /dev/null; then
    log "   [OK] Integridad verificada"
else
    log "   [ERROR] Archivo corrupto"
    exit 1
fi
mv "$ARCHIVE_TMP" "$ARCHIVE"
(cd "$DAILY_DIR" && sha256sum "$BACKUP_NAME.tar.gz" > "$BACKUP_NAME.tar.gz.sha256")
rm -rf "$BACKUP_DIR"
log "   [OK] Guardado: $ARCHIVE"

# Paso 4: Backup semanal local (enlace duro: no duplica espacio; los domingos)
if [[ "$DAY_OF_WEEK" -eq 7 ]]; then
    log "4. Registrando backup semanal..."
    ln "$ARCHIVE" "$WEEKLY_DIR/"
    ln "$ARCHIVE.sha256" "$WEEKLY_DIR/"
    log "   [OK] Enlazado en $WEEKLY_DIR"
fi

# Paso 5: Subida a Cloudflare R2. Un fallo aquí NO detiene lo local.
# CLOUD_STATUS: ok | disabled | failed
CLOUD_STATUS="disabled"
if [[ "$CLOUD_BACKUP" == "true" ]]; then
    log "5. Subiendo a R2..."
    if upload_to_r2; then
        CLOUD_STATUS="ok"
        log "   [OK] Subido a R2"
    else
        CLOUD_STATUS="failed"
        log "   [ERROR] falló la subida a R2 (el backup local está a salvo)"
    fi
else
    log "5. [AVISO] Nube DESHABILITADA (CLOUD_BACKUP=false): solo hay copia local"
fi

# Paso 6: Retención por cantidad. La local siempre; la remota solo si la
# subida salió bien (si el backup nuevo no está en R2, no se borran los viejos).
log "6. Aplicando retención..."
prune_local "$DAILY_DIR" "$RETENTION_DIARIO"
if [[ "$DAY_OF_WEEK" -eq 7 ]]; then
    prune_local "$WEEKLY_DIR" "$RETENTION_SEMANAL"
fi
if [[ "$CLOUD_STATUS" == "ok" ]]; then
    prune_remote "daily" "$RETENTION_DIARIO" || CLOUD_STATUS="failed"
    if [[ "$DAY_OF_WEEK" -eq 7 ]]; then
        prune_remote "weekly" "$RETENTION_SEMANAL" || CLOUD_STATUS="failed"
    fi
    if [[ "$CLOUD_STATUS" == "failed" ]]; then
        log "   [ERROR] falló la retención en R2"
    fi
fi
log "   [OK] Retención local aplicada"

case "$CLOUD_STATUS" in
    ok)       log "=== Backup completado exitosamente ==="; EXIT_CODE=0 ;;
    disabled) log "=== Backup LOCAL completado (nube deshabilitada) ==="; EXIT_CODE=0 ;;
    failed)   log "=== Backup LOCAL completado; falló la nube (revisar R2) ==="; EXIT_CODE=2 ;;
esac
log "Archivo generado:"
ls -lh "$ARCHIVE" | tee -a "$LOG_FILE"
exit "$EXIT_CODE"
