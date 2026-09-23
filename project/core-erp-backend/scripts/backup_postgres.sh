#!/usr/bin/env bash
# Backup automatizado de Postgres con retención — otra pieza de "Postgres
# como punto único de falla": streaming replication (ver
# setup_read_replica.sh) protege contra la caída de la instancia y
# reparte lecturas, pero NO protege contra corrupción de datos o un
# DELETE/DROP accidental que se replica igual a la réplica en segundos.
# Eso lo cubre un backup lógico independiente, con puntos de restauración
# en el tiempo.
#
# Uso:
#   ./scripts/backup_postgres.sh                    # backup de ERP_DATABASE_URL (o erp_educativo por defecto)
#   BACKUP_RETENTION_DAYS=14 ./scripts/backup_postgres.sh
#   BACKUP_DIR=/mnt/backups ./scripts/backup_postgres.sh
#
# Pensado para correr por cron (ej. diario a las 3am):
#   0 3 * * * BACKUP_DIR=/var/backups/erp /path/to/backup_postgres.sh >> /var/log/erp_backup.log 2>&1
#
# Probado en este sandbox contra Postgres real (ver
# tests/test_backup_restore.sh): produce un dump con pg_dump -Fc
# (formato custom, comprimido, restaurable con pg_restore), y confirma
# que restaurar ese dump en una base nueva reproduce los datos.
set -euo pipefail

DB_HOST="${ERP_DB_HOST:-localhost}"
DB_PORT="${ERP_DB_PORT:-5432}"
DB_USER="${ERP_DB_USER:-postgres}"
DB_NAME="${ERP_DB_NAME:-erp_educativo}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/erp-educativo}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

mkdir -p "${BACKUP_DIR}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"

echo "Iniciando backup de '${DB_NAME}' -> ${BACKUP_FILE}"
PGPASSWORD="${ERP_DB_PASSWORD:-postgres}" pg_dump \
  -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
  -Fc --no-owner --no-privileges \
  -f "${BACKUP_FILE}" \
  "${DB_NAME}"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "Backup completado: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Verificación mínima: un dump de formato custom corrupto o truncado
# falla al listar su contenido con pg_restore --list. Sin esta
# verificación, un backup roto se descubre recién el día que hace falta
# restaurarlo — que es el peor momento posible para enterarse.
if ! pg_restore --list "${BACKUP_FILE}" > /dev/null 2>&1; then
  echo "ERROR: el backup generado no pasa la verificación de integridad (pg_restore --list falló)" >&2
  exit 1
fi
echo "Verificación de integridad OK."

echo "Aplicando retención de ${RETENTION_DAYS} días..."
DELETED_COUNT=0
while IFS= read -r old_file; do
  rm -f "${old_file}"
  DELETED_COUNT=$((DELETED_COUNT + 1))
  echo "  eliminado (retención vencida): ${old_file}"
done < <(find "${BACKUP_DIR}" -name "${DB_NAME}_*.dump" -mtime "+${RETENTION_DAYS}")

echo "Backups eliminados por retención: ${DELETED_COUNT}"
echo "Backups vigentes: $(find "${BACKUP_DIR}" -name "${DB_NAME}_*.dump" | wc -l)"
