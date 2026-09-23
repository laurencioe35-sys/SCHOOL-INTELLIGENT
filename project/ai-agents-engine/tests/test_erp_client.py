"""
Tests de config/erp_client.py.

Igual que test_resilience_redis.py prueba contra un Redis real en vez de
mockear la librería, este archivo levanta un servidor HTTP real (stdlib,
en un hilo, en un puerto libre de localhost) para ejercitar el cliente de
punta a punta: request saliente, headers, body, y manejo de errores HTTP
y de conexión — no se mockea `urllib` directamente.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from config.erp_client import ErpClient, get_default_client


class _FakeErpHandler(BaseHTTPRequestHandler):
    """Simula exactamente el contrato de
    core-erp-backend/api/grades.py:/grades/submit-from-agent."""

    received: list[dict] = []

    def log_message(self, format, *args):  # silencia el log de acceso en stdout
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        key = self.headers.get("X-Internal-Service-Key")
        _FakeErpHandler.received.append({"path": self.path, "body": body, "key": key})

        if key != "correct-key":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(json.dumps({"detail": "Clave de servicio interna inválida"}).encode())
            return

        if body.get("student_id") == "alumno-no-matriculado":
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"detail": "El alumno no está matriculado en esta aula"}).encode())
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "buffered", "queue_length": 1}).encode())


@pytest.fixture
def fake_erp_server():
    _FakeErpHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _FakeErpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=2)


def test_unconfigured_client_does_not_attempt_connection():
    client = ErpClient(base_url="", internal_key="")
    result = client.submit_grading_result(
        student_id="s1", classroom_id="c1", score_0_to_1=0.8, feedback="bien"
    )
    assert result.ok is False
    assert result.error == "erp_client_not_configured"


def test_successful_submission_reaches_server_with_expected_payload(fake_erp_server):
    client = ErpClient(base_url=fake_erp_server, internal_key="correct-key")
    result = client.submit_grading_result(
        student_id="s1", classroom_id="c1", score_0_to_1=0.9,
        feedback="Cubrió los puntos clave", needs_teacher_review=False, session_id="sess-1",
    )
    assert result.ok is True
    assert result.status_code == 200
    assert result.response == {"status": "buffered", "queue_length": 1}

    assert len(_FakeErpHandler.received) == 1
    req = _FakeErpHandler.received[0]
    assert req["path"] == "/grades/submit-from-agent"
    assert req["key"] == "correct-key"
    assert req["body"] == {
        "student_id": "s1",
        "classroom_id": "c1",
        "score_0_to_1": 0.9,
        "feedback": "Cubrió los puntos clave",
        "needs_teacher_review": False,
        "session_id": "sess-1",
    }


def test_wrong_internal_key_surfaces_as_failed_sync_not_exception(fake_erp_server):
    client = ErpClient(base_url=fake_erp_server, internal_key="wrong-key")
    result = client.submit_grading_result(
        student_id="s1", classroom_id="c1", score_0_to_1=0.5, feedback="x"
    )
    assert result.ok is False
    assert result.status_code == 401


def test_unenrolled_student_surfaces_erp_validation_error(fake_erp_server):
    client = ErpClient(base_url=fake_erp_server, internal_key="correct-key")
    result = client.submit_grading_result(
        student_id="alumno-no-matriculado", classroom_id="c1", score_0_to_1=0.5, feedback="x"
    )
    assert result.ok is False
    assert result.status_code == 400
    assert "matriculado" in result.error


def test_server_unreachable_fails_gracefully_without_raising():
    # Puerto en localhost donde deliberadamente no hay nada escuchando.
    client = ErpClient(base_url="http://127.0.0.1:1", internal_key="correct-key", timeout_seconds=1.0)
    result = client.submit_grading_result(
        student_id="s1", classroom_id="c1", score_0_to_1=0.5, feedback="x"
    )
    assert result.ok is False
    assert result.error is not None


def test_get_default_client_is_a_singleton_built_from_env(monkeypatch):
    import config.erp_client as erp_client_module
    monkeypatch.setattr(erp_client_module, "_default_client", None)
    monkeypatch.setenv("ERP_API_BASE_URL", "http://example-erp:8200")
    monkeypatch.setenv("AI_AGENTS_INTERNAL_KEY", "shared-secret")

    client = get_default_client()
    assert client.base_url == "http://example-erp:8200"
    assert client.internal_key == "shared-secret"
    assert get_default_client() is client
