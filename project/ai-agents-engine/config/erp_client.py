"""
Cliente HTTP hacia core-erp-backend — el punto de integración que faltaba
entre el resultado de un agente (ej. GradingResult de grading_agent) y el
ERP real.

Antes: GradingAgent.handle() calificaba la respuesta y devolvía un
GradingResult, pero nada en el proyecto lo mandaba a ningún lado más allá
del blackboard en memoria (que solo vive dentro de este proceso, para que
AnalyticsAgent agregue métricas del mismo ciclo). El ERP nunca se
enteraba de la nota generada por IA.

Ahora: `submit_grading_result()` hace ese último salto — un POST a
`{ERP_API_BASE_URL}/grades/submit-from-agent` en core-erp-backend (ver
api/grades.py de ese proyecto), autenticado con un secreto compartido de
servicio (no un JWT de usuario: este cliente no actúa en nombre de ningún
profesor concreto).

Mismo patrón de honestidad que llm_client.py: si el ERP no está
configurado (o no responde), esto NO debe tumbar el pipeline de
calificación — el agente ya hizo su trabajo (calificar) y ese resultado
sigue siendo válido y visible en el blackboard/output_queue aunque la
sincronización con el ERP falle. El fallo se loguea y se cuenta, no se
oculta.
"""
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("ai_agents_engine.erp_client")

DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass
class ErpSyncResult:
    ok: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    response: Optional[dict[str, Any]] = None


class ErpClient:
    """Cliente delgado y sin dependencias externas (usa `urllib` de la
    librería estándar, no `requests`, para no forzar esa dependencia en
    todos los despliegues del ai-agents-engine — el resto del proyecto
    usa `requests` para el LLM, pero aquí basta con un POST simple).

    Se construye desde variables de entorno por defecto (mismo patrón de
    fábrica que `build_circuit_breaker` en el core-erp-backend):
      - ERP_API_BASE_URL: URL base del core-erp-backend, ej.
        "http://core-erp-backend:8200" en docker-compose/K8s.
      - AI_AGENTS_INTERNAL_KEY: secreto compartido con ese servicio (debe
        ser IDÉNTICO al configurado allá — ver api/grades.py).

    Si ERP_API_BASE_URL no está configurada, el cliente queda en modo
    "deshabilitado" (no intenta conectarse a nada) y cada llamada retorna
    `ErpSyncResult(ok=False, error="erp_client_not_configured")` de
    inmediato — igual de determinista que el modo mock del LLM.
    """

    def __init__(
        self,
        base_url: str | None = None,
        internal_key: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.base_url = (base_url if base_url is not None else os.getenv("ERP_API_BASE_URL", "")).rstrip("/")
        self.internal_key = internal_key if internal_key is not None else os.getenv("AI_AGENTS_INTERNAL_KEY", "")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.internal_key)

    def submit_grading_result(
        self,
        *,
        student_id: str,
        classroom_id: str,
        score_0_to_1: float,
        feedback: str,
        needs_teacher_review: bool = False,
        session_id: str | None = None,
    ) -> ErpSyncResult:
        if not self.configured:
            return ErpSyncResult(ok=False, error="erp_client_not_configured")

        payload = {
            "student_id": student_id,
            "classroom_id": classroom_id,
            "score_0_to_1": score_0_to_1,
            "feedback": feedback,
            "needs_teacher_review": needs_teacher_review,
            "session_id": session_id,
        }
        url = f"{self.base_url}/grades/submit-from-agent"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Internal-Service-Key": self.internal_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8") or "{}")
                return ErpSyncResult(ok=True, status_code=resp.status, response=body)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.warning("ERP rechazó la nota (HTTP %s): %s", exc.code, detail)
            return ErpSyncResult(ok=False, status_code=exc.code, error=detail)
        except urllib.error.URLError as exc:
            logger.warning("No se pudo conectar al core-erp-backend en %s: %s", url, exc.reason)
            return ErpSyncResult(ok=False, error=str(exc.reason))
        except Exception as exc:  # noqa: BLE001 - nunca debe tumbar al agente que llama
            logger.warning("Fallo inesperado sincronizando nota con el ERP: %s", exc)
            return ErpSyncResult(ok=False, error=str(exc))


_default_client: ErpClient | None = None


def get_default_client() -> ErpClient:
    """Cliente singleton construido desde variables de entorno — lo que
    usan los agentes por defecto. Separado para poder inyectar un cliente
    de prueba (ver tests/test_erp_client.py) sin tocar variables globales
    de entorno en cada test."""
    global _default_client
    if _default_client is None:
        _default_client = ErpClient()
    return _default_client
