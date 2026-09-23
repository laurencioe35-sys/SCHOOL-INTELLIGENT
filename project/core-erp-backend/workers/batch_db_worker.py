"""
Batch worker: consolidador de notas.

Corre en un proceso separado del API (en producción: un Deployment de K8s
aparte, o un cronjob cada N segundos). Vacía el buffer de Redis y escribe
en lote a la base de datos relacional, que es una operación mucho más
barata que N escrituras individuales.

Se puede correr una sola vez (`python batch_db_worker.py --once`) o en
loop continuo (`python batch_db_worker.py`).
"""
import json
import os
import sys
import time

import redis
from sqlalchemy.orm import Session
from prometheus_client import start_http_server

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal, init_db  # noqa: E402
from database.models import Grade, GradeStatus, GradedBy  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from observability.metrics import grades_consolidated_total, grades_dead_letter_total  # noqa: E402
from observability.logging_config import log_event  # noqa: E402

# El batch worker corre en un proceso SEPARADO del API (por diseño, para
# que un pico de consolidación no compita por CPU con requests HTTP), así
# que no puede compartir el endpoint /metrics del API — necesita su propio
# puerto de exposición Prometheus.
METRICS_PORT = int(os.getenv("BATCH_WORKER_METRICS_PORT", "9100"))

REDIS_URL = os.getenv("ERP_REDIS_URL", "redis://localhost:6379/0")
PENDING_QUEUE_KEY = "grades:pending"
BATCH_SIZE = 100
POLL_INTERVAL_SECONDS = 2


DEAD_LETTER_QUEUE_KEY = "grades:dead_letter"


def consolidate_batch(db: Session, r: redis.Redis) -> int:
    """Consolida hasta BATCH_SIZE notas.

    IMPORTANTE (hallazgo real durante pruebas): en SQLite, una nota con un
    student_id inexistente se insertaba igual porque SQLite no valida
    foreign keys por defecto. Al migrar a Postgres, esa misma nota rompía
    TODO el lote con IntegrityError, porque un INSERT ... VALUES (...), (...)
    de múltiples filas es una sola transacción: si una fila falla, Postgres
    revierte las demás también.

    La corrección real es procesar y hacer commit de a una fila, para que
    un evento corrupto no tumbe el resto del lote, y mandar el evento malo
    a una cola separada (`grades:dead_letter`) para poder inspeccionarlo
    después en vez de perderlo silenciosamente.
    """
    committed_count = 0
    for _ in range(BATCH_SIZE):
        raw = r.lpop(PENDING_QUEUE_KEY)
        if raw is None:
            break
        event = json.loads(raw)
        grade = Grade(
            student_id=event["student_id"],
            classroom_id=event["classroom_id"],
            score=event["score"],
            status=GradeStatus.committed,
            committed_at=datetime.now(timezone.utc),
            graded_by=GradedBy(event.get("graded_by", "teacher")),
            feedback=event.get("feedback"),
            needs_teacher_review=event.get("needs_teacher_review", False),
        )
        db.add(grade)
        try:
            db.commit()
            committed_count += 1
            grades_consolidated_total.inc()
        except Exception as exc:  # noqa: BLE001 - loggeamos y seguimos con el resto del lote
            db.rollback()
            event["error"] = str(exc.__cause__ or exc)
            r.rpush(DEAD_LETTER_QUEUE_KEY, json.dumps(event))
            grades_dead_letter_total.inc()
            log_event(
                "grade_moved_to_dead_letter",
                student_id=event["student_id"],
                classroom_id=event.get("classroom_id"),
                error=event["error"],
            )
            print(f"[batch_db_worker] Evento inválido movido a dead-letter: {event['student_id']}")

    if committed_count:
        log_event("grades_batch_consolidated", count=committed_count)
    return committed_count


def run_once():
    init_db()
    r = redis.from_url(REDIS_URL, decode_responses=True)
    db = SessionLocal()
    try:
        count = consolidate_batch(db, r)
        print(f"[batch_db_worker] Consolidadas {count} notas.")
        return count
    finally:
        db.close()


def run_loop():
    start_http_server(METRICS_PORT)
    print(f"[batch_db_worker] Métricas Prometheus expuestas en :{METRICS_PORT}/metrics")
    print("[batch_db_worker] Iniciando loop de consolidación cada "
          f"{POLL_INTERVAL_SECONDS}s ...")
    while True:
        run_once()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()
