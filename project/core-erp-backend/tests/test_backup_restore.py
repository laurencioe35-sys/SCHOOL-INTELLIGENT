"""
Test end-to-end real del backup y restauración de Postgres.

Corre `scripts/backup_postgres.sh` de verdad vía subprocess (no reimplementa
su lógica en Python), restaura el dump resultante en una base temporal, y
confirma que un dato insertado antes del backup aparece intacto después
de restaurar — la prueba real de que un backup "sirve" no es que el
archivo exista, es que se pueda reconstruir el estado desde él.
"""
import os
import shutil
import subprocess
import tempfile
import uuid

import pytest
import psycopg2

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "backup_postgres.sh")
DB_NAME = "erp_educativo_test"
CONN_KWARGS = dict(host="localhost", port=5432, user="postgres", password="postgres")


def _psql_available():
    return shutil.which("pg_dump") is not None and shutil.which("pg_restore") is not None


@pytest.mark.skipif(not _psql_available(), reason="pg_dump/pg_restore no están en PATH en este entorno")
def test_backup_then_restore_preserves_data():
    marker = f"backup_marker_{uuid.uuid4().hex[:8]}"

    conn = psycopg2.connect(dbname=DB_NAME, **CONN_KWARGS)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS backup_smoke_test (id serial primary key, marker text)")
        cur.execute("INSERT INTO backup_smoke_test (marker) VALUES (%s)", (marker,))
    conn.close()

    with tempfile.TemporaryDirectory() as backup_dir:
        env = {
            **os.environ,
            "ERP_DB_PASSWORD": "postgres",
            "ERP_DB_NAME": DB_NAME,
            "BACKUP_DIR": backup_dir,
            "BACKUP_RETENTION_DAYS": "7",
        }
        result = subprocess.run(["bash", SCRIPT_PATH], env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, f"backup_postgres.sh falló:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        assert "Verificación de integridad OK." in result.stdout

        dump_files = [f for f in os.listdir(backup_dir) if f.endswith(".dump")]
        assert len(dump_files) == 1
        dump_path = os.path.join(backup_dir, dump_files[0])

        restore_db_name = f"erp_restore_test_{uuid.uuid4().hex[:8]}"
        admin_conn = psycopg2.connect(dbname="postgres", **CONN_KWARGS)
        admin_conn.autocommit = True
        try:
            with admin_conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{restore_db_name}"')

            restore = subprocess.run(
                ["pg_restore", "-h", "localhost", "-U", "postgres", "-d", restore_db_name, dump_path],
                env={**os.environ, "PGPASSWORD": "postgres"},
                capture_output=True, text=True, timeout=60,
            )
            assert restore.returncode == 0, f"pg_restore falló:\n{restore.stderr}"

            check_conn = psycopg2.connect(dbname=restore_db_name, **CONN_KWARGS)
            try:
                with check_conn.cursor() as cur:
                    cur.execute("SELECT marker FROM backup_smoke_test WHERE marker = %s", (marker,))
                    row = cur.fetchone()
                assert row is not None, "el dato insertado antes del backup no apareció después de restaurar"
                assert row[0] == marker
            finally:
                check_conn.close()
        finally:
            with admin_conn.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{restore_db_name}"')
            admin_conn.close()

    cleanup_conn = psycopg2.connect(dbname=DB_NAME, **CONN_KWARGS)
    cleanup_conn.autocommit = True
    with cleanup_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS backup_smoke_test")
    cleanup_conn.close()


@pytest.mark.skipif(not _psql_available(), reason="pg_dump/pg_restore no están en PATH en este entorno")
def test_backup_applies_retention_policy():
    """Crea dumps 'viejos' a mano (con mtime alterado) y confirma que el
    script los elimina según BACKUP_RETENTION_DAYS, dejando solo el
    recién creado."""
    import time

    with tempfile.TemporaryDirectory() as backup_dir:
        old_dump = os.path.join(backup_dir, f"{DB_NAME}_20200101T000000Z.dump")
        with open(old_dump, "wb") as f:
            f.write(b"contenido de un dump viejo, no valido, no importa para este test")
        ten_days_ago = time.time() - 10 * 86400
        os.utime(old_dump, (ten_days_ago, ten_days_ago))

        env = {
            **os.environ,
            "ERP_DB_PASSWORD": "postgres",
            "ERP_DB_NAME": DB_NAME,
            "BACKUP_DIR": backup_dir,
            "BACKUP_RETENTION_DAYS": "7",
        }
        result = subprocess.run(["bash", SCRIPT_PATH], env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        assert not os.path.exists(old_dump), "el dump con más de 7 días debió eliminarse por retención"

        remaining = [f for f in os.listdir(backup_dir) if f.endswith(".dump")]
        assert len(remaining) == 1  # solo el que el script acaba de crear
