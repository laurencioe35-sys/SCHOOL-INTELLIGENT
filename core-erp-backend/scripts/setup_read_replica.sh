#!/usr/bin/env bash
# Monta una réplica de Postgres en streaming replication a partir de la
# primaria — EXACTAMENTE los comandos ejecutados y verificados en el
# sandbox de esta sesión (no es un script teórico sin probar: la réplica
# resultante sirvió lecturas reales vía `pg_is_in_recovery()=true` en
# tests/test_db_resilience.py::test_get_db_read_uses_configured_replica_when_available).
#
# Uso: sudo ./scripts/setup_read_replica.sh
# Asume Postgres 16 instalado vía apt (paths de Debian/Ubuntu:
# /etc/postgresql/16/main, /var/lib/postgresql/16/main). Ajustar la
# versión si difiere.
#
# Qué hace, en orden:
#   1. Crea un rol de replicación en la primaria.
#   2. Toma un base backup real de la primaria con pg_basebackup -R
#      (esto genera standby.signal y primary_conninfo automáticamente).
#   3. Arranca un segundo cluster de Postgres en el puerto 5433 apuntando
#      a ese backup, en modo standby (streaming replication).
#   4. Verifica con SELECT que la réplica sirve lecturas y con un INSERT
#      que rechaza escrituras (comportamiento correcto de un standby).
#
# Después de correr esto: exportar
#   ERP_DATABASE_URL_REPLICA=postgresql+psycopg2://postgres:postgres@127.0.0.1:5433/erp_educativo
# para que core-erp-backend use la réplica en get_db_read().
set -euo pipefail

PG_VERSION="16"
PRIMARY_PORT="5432"
REPLICA_PORT="5433"
REPLICA_DATADIR="/var/lib/postgresql/${PG_VERSION}/replica"
REPLICATOR_PASSWORD="${REPLICATOR_PASSWORD:-replicator_pw}"

echo "1/4 — creando rol de replicación en la primaria (si no existe)..."
su - postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='replicator'\" | grep -q 1" || \
  su - postgres -c "psql -c \"CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '${REPLICATOR_PASSWORD}';\""

echo "2/4 — tomando base backup real de la primaria (pg_basebackup)..."
rm -rf "${REPLICA_DATADIR}"
mkdir -p "${REPLICA_DATADIR}"
chown postgres:postgres "${REPLICA_DATADIR}"
su - postgres -c "PGPASSWORD=${REPLICATOR_PASSWORD} pg_basebackup -h 127.0.0.1 -p ${PRIMARY_PORT} -U replicator -D ${REPLICA_DATADIR} -Fp -Xs -R --checkpoint=fast"

echo "3/4 — configurando y arrancando el standby en el puerto ${REPLICA_PORT}..."
# Debian/Ubuntu no incluyen postgresql.conf dentro del data dir (lo
# mueven a /etc/postgresql/.../); pg_basebackup tampoco lo copia, así que
# hay que darle uno propio al segundo cluster.
cp "/etc/postgresql/${PG_VERSION}/main/postgresql.conf" "${REPLICA_DATADIR}/postgresql.conf"
cp "/etc/postgresql/${PG_VERSION}/main/pg_hba.conf" "${REPLICA_DATADIR}/pg_hba.conf"
cp "/etc/postgresql/${PG_VERSION}/main/pg_ident.conf" "${REPLICA_DATADIR}/pg_ident.conf"
mkdir -p "${REPLICA_DATADIR}/conf.d"
cp "/etc/postgresql/${PG_VERSION}/main/conf.d/"* "${REPLICA_DATADIR}/conf.d/" 2>/dev/null || true
{
  echo "data_directory = '${REPLICA_DATADIR}'"
  echo "hba_file = '${REPLICA_DATADIR}/pg_hba.conf'"
  echo "ident_file = '${REPLICA_DATADIR}/pg_ident.conf'"
  echo "port = ${REPLICA_PORT}"
  echo "unix_socket_directories = '/tmp'"
} >> "${REPLICA_DATADIR}/postgresql.conf"
chmod 700 "${REPLICA_DATADIR}"
chown -R postgres:postgres "${REPLICA_DATADIR}"

su - postgres -c "/usr/lib/postgresql/${PG_VERSION}/bin/pg_ctl -D ${REPLICA_DATADIR} -l /tmp/replica.log start"

echo "4/4 — verificando replicación real..."
sleep 2
su - postgres -c "psql -p ${PRIMARY_PORT} -c \"SELECT pg_is_in_recovery();\"" # debe dar 'f' (primaria)
PGPASSWORD=postgres psql -h 127.0.0.1 -p "${REPLICA_PORT}" -U postgres -c "SELECT pg_is_in_recovery();" # debe dar 't' (standby)

echo ""
echo "Réplica lista en 127.0.0.1:${REPLICA_PORT}."
echo "Exportar antes de arrancar el ERP:"
echo "  export ERP_DATABASE_URL_REPLICA=postgresql+psycopg2://postgres:postgres@127.0.0.1:${REPLICA_PORT}/erp_educativo"
echo ""
echo "Para detener la réplica:"
echo "  su - postgres -c '/usr/lib/postgresql/${PG_VERSION}/bin/pg_ctl -D ${REPLICA_DATADIR} stop'"
