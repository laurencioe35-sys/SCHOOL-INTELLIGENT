"""
Tests del rate limiting — NUEVO, no existía en el proyecto.

Corre contra el mismo Postgres/Redis reales que tests/test_erp.py (ver
ese archivo para la configuración de entorno). Los límites se ajustan
por test con `monkeypatch.setenv(...)` a valores pequeños para no tener
que esperar una ventana de 60s real en cada test — `_rate_limit_config()`
en main.py lee el entorno en cada request justo para permitir esto.

Correr con: pytest -v tests/test_rate_limit.py (con Postgres y Redis reales)
"""
import os

os.environ["ERP_DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo_test"
os.environ["ERP_REDIS_URL"] = "redis://localhost:6379/1"

import time

import pytest
import redis
from fastapi.testclient import TestClient

from database.connection import engine
from database.models import Base
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    r = redis.from_url(os.environ["ERP_REDIS_URL"])
    r.flushdb()
    # Ventana chica para que los tests corran en segundos, no en minutos.
    monkeypatch.setenv("ERP_RATE_LIMIT_WINDOW_SECONDS", "2")
    yield


def _register_teacher(organization_name: str, email: str = "teacher@test.pe") -> str:
    resp = client.post("/auth/register", json={
        "full_name": "Prof. Test", "email": email, "password": "clave123",
        "role": "teacher", "organization_name": organization_name,
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_requests_within_limit_are_allowed(monkeypatch):
    monkeypatch.setenv("ERP_RATE_LIMIT_PER_ORG_PER_MIN", "5")
    token = _register_teacher("Colegio Límite Normal")

    for _ in range(5):
        resp = client.get("/students", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.status_code != 429


def test_exceeding_org_limit_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setenv("ERP_RATE_LIMIT_PER_ORG_PER_MIN", "3")
    token = _register_teacher("Colegio Límite Bajo")
    headers = {"Authorization": f"Bearer {token}"}

    # El registro (login) ya consumió 1 request contra el límite "auth_ip"
    # (no el de "org", porque en ese momento aún no había token) — así que
    # las primeras 3 peticiones CON token deberían pasar.
    statuses = [client.get("/students", headers=headers).status_code for _ in range(3)]
    assert 429 not in statuses

    blocked = client.get("/students", headers=headers)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert int(blocked.headers["Retry-After"]) >= 0


def test_different_organizations_have_independent_buckets(monkeypatch):
    """Un colegio saturando su cuota no debe afectar a otro — este es
    justo el problema real que el rate limiting resuelve (multi-tenancy
    sin esto compartía el mismo 'presupuesto' de facto)."""
    monkeypatch.setenv("ERP_RATE_LIMIT_PER_ORG_PER_MIN", "2")
    token_a = _register_teacher("Colegio A", email="teacher-a@test.pe")
    token_b = _register_teacher("Colegio B", email="teacher-b@test.pe")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Colegio A satura su cuota de 2.
    client.get("/students", headers=headers_a)
    client.get("/students", headers=headers_a)
    blocked_a = client.get("/students", headers=headers_a)
    assert blocked_a.status_code == 429

    # Colegio B, que nunca pidió nada, sigue teniendo su cuota completa.
    fresh_b = client.get("/students", headers=headers_b)
    assert fresh_b.status_code != 429


def test_window_resets_after_expiration(monkeypatch):
    monkeypatch.setenv("ERP_RATE_LIMIT_PER_ORG_PER_MIN", "1")
    monkeypatch.setenv("ERP_RATE_LIMIT_WINDOW_SECONDS", "1")
    token = _register_teacher("Colegio Ventana Corta")
    headers = {"Authorization": f"Bearer {token}"}

    first = client.get("/students", headers=headers)
    assert first.status_code != 429
    blocked = client.get("/students", headers=headers)
    assert blocked.status_code == 429

    time.sleep(1.2)  # pasa la ventana de 1s

    after_reset = client.get("/students", headers=headers)
    assert after_reset.status_code != 429


def test_login_endpoint_has_its_own_stricter_per_ip_limit(monkeypatch):
    """Protección de fuerza bruta: /auth/login (y /auth/register) se
    limitan por IP con un umbral propio (auth_ip), independiente del
    límite general de IP no autenticada — antes de este cambio no
    existía ningún límite aquí. Ambos endpoints comparten el mismo
    bucket por IP a propósito: un atacante no puede evadir el límite de
    login alternando con registros falsos."""
    monkeypatch.setenv("ERP_RATE_LIMIT_AUTH_PER_IP_PER_MIN", "4")
    _register_teacher("Colegio Fuerza Bruta", email="victima@test.pe")  # consume 1/4 del bucket auth_ip

    attempts = [
        client.post("/auth/login", json={"email": "victima@test.pe", "password": "clave-incorrecta"})
        for _ in range(3)
    ]
    assert all(r.status_code == 401 for r in attempts)  # credenciales malas, pero NO rate-limited todavía (2,3,4 de 4)

    blocked = client.post("/auth/login", json={"email": "victima@test.pe", "password": "clave-incorrecta"})
    assert blocked.status_code == 429


def test_general_unauthenticated_and_auth_endpoints_use_separate_buckets(monkeypatch):
    """El límite estricto de /auth/login no debe contaminar ni ser
    contaminado por tráfico anónimo a otras rutas desde la misma IP."""
    monkeypatch.setenv("ERP_RATE_LIMIT_AUTH_PER_IP_PER_MIN", "2")
    monkeypatch.setenv("ERP_RATE_LIMIT_PER_IP_PER_MIN", "50")

    # Satura el bucket "auth_ip" de /auth/login.
    client.post("/auth/login", json={"email": "nadie@test.pe", "password": "x"})
    client.post("/auth/login", json={"email": "nadie@test.pe", "password": "x"})
    blocked = client.post("/auth/login", json={"email": "nadie@test.pe", "password": "x"})
    assert blocked.status_code == 429

    # La raíz "/" está exenta explícitamente; probamos con una ruta
    # anónima real y no exenta para confirmar que NO comparte contador.
    unrelated = client.get("/nonexistent-path-para-probar-bucket-ip")
    assert unrelated.status_code != 429  # 404, pero no 429


def test_metrics_and_root_paths_are_exempt(monkeypatch):
    monkeypatch.setenv("ERP_RATE_LIMIT_PER_IP_PER_MIN", "1")
    # Con límite de 1 por minuto, si /metrics contara, la 2da llamada
    # ya estaría bloqueada — no debe estarlo porque está exenta.
    for _ in range(5):
        resp = client.get("/metrics")
        assert resp.status_code == 200
    for _ in range(5):
        resp = client.get("/")
        assert resp.status_code == 200


def test_rate_limiter_fails_open_when_redis_unavailable(monkeypatch):
    """Fail-open deliberado: si Redis no responde, la petición se deja
    pasar en vez de tumbar el servicio completo (ver docstring de
    RateLimiter en observability/rate_limiter.py)."""
    import main as main_module

    monkeypatch.setenv("ERP_RATE_LIMIT_PER_ORG_PER_MIN", "1")
    token = _register_teacher("Colegio Redis Caido")
    headers = {"Authorization": f"Bearer {token}"}

    class BrokenRedis:
        def incr(self, *_a, **_k):
            raise ConnectionError("Redis no disponible (simulado)")

        def expire(self, *_a, **_k):
            raise ConnectionError("Redis no disponible (simulado)")

    original_redis = main_module._rate_limiter._r
    main_module._rate_limiter._r = BrokenRedis()
    try:
        # Aunque el límite es 1, con Redis roto TODAS las peticiones
        # deben pasar (fail-open) en vez de devolver 429 o 500.
        for _ in range(5):
            resp = client.get("/students", headers=headers)
            assert resp.status_code != 429
    finally:
        main_module._rate_limiter._r = original_redis
