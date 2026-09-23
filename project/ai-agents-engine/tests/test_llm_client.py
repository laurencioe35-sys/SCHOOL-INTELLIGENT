"""
Tests del proveedor LLM de respaldo.

Ningún test de este archivo hace red real: se inyectan funciones falsas
en `_call_anthropic`/`_call_openai_compatible` (el punto exacto donde
`call_llm` llamaría a la red), igual que el resto del proyecto prueba el
modo mock sin una API key real. Lo que se prueba es la LÓGICA de
selección de proveedor, failover y circuit breaker — no la integración
HTTP con Anthropic/OpenAI, que sigue sin ejercitarse en este entorno.
"""
import json

import pytest

from config import llm_client


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Cada test arranca sin proveedores configurados y sin breakers
    abiertos de un test anterior."""
    for var in (
        "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
        "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL",
        "ANTHROPIC_FALLBACK_API_KEY", "ANTHROPIC_FALLBACK_MODEL",
        "LLM_CIRCUIT_FAILURE_THRESHOLD", "LLM_CIRCUIT_RESET_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    llm_client.reset_circuit_breakers()
    yield
    llm_client.reset_circuit_breakers()


def test_no_providers_configured_uses_mock():
    """Comportamiento preexistente preservado: sin ninguna API key, se
    usa el mock — no debe intentar llamar a ningún proveedor real."""
    result = llm_client.call_llm('{"action": ...}', "Vamos a ver un triangulo")
    data = json.loads(result)
    assert data["action"] == "render_3d_object"


def test_primary_success_does_not_touch_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-primary-fake")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fallback-fake")

    def fake_primary(sp, ut, api_key, model):
        assert api_key == "sk-primary-fake"
        return json.dumps({"from": "primary"})

    def fake_fallback(*a, **k):
        raise AssertionError("no debería llamarse al respaldo si el primario funciona")

    monkeypatch.setattr(llm_client, "_call_anthropic", fake_primary)
    monkeypatch.setattr(llm_client, "_call_openai_compatible", fake_fallback)

    result = json.loads(llm_client.call_llm("system", "user"))
    assert result == {"from": "primary"}


def test_fallback_used_when_primary_raises(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-primary-fake")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fallback-fake")

    def failing_primary(sp, ut, api_key, model):
        raise TimeoutError("primario no responde")

    def working_fallback(sp, ut, api_key, model, base_url):
        return json.dumps({"from": "fallback"})

    monkeypatch.setattr(llm_client, "_call_anthropic", failing_primary)
    monkeypatch.setattr(llm_client, "_call_openai_compatible", working_fallback)

    result = json.loads(llm_client.call_llm("system", "user"))
    assert result == {"from": "fallback"}

    breaker = llm_client._get_breaker("anthropic_primary")
    assert breaker.consecutive_failures == 1


def test_anthropic_fallback_used_when_openai_not_configured(monkeypatch):
    """Si no hay OPENAI_API_KEY, el respaldo es una segunda cuenta de
    Anthropic (ANTHROPIC_FALLBACK_API_KEY), no directamente el mock."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-primary-fake")
    monkeypatch.setenv("ANTHROPIC_FALLBACK_API_KEY", "sk-secondary-fake")

    calls = []

    def primary_or_fallback(sp, ut, api_key, model):
        calls.append(api_key)
        if api_key == "sk-primary-fake":
            raise ConnectionError("cuenta primaria con rate limit")
        return json.dumps({"used_key": api_key})

    monkeypatch.setattr(llm_client, "_call_anthropic", primary_or_fallback)

    result = json.loads(llm_client.call_llm("system", "user"))
    assert result == {"used_key": "sk-secondary-fake"}
    assert calls == ["sk-primary-fake", "sk-secondary-fake"]


def test_falls_back_to_mock_when_all_real_providers_fail(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-primary-fake")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fallback-fake")

    monkeypatch.setattr(llm_client, "_call_anthropic",
                         lambda *a, **k: (_ for _ in ()).throw(TimeoutError("caído")))
    monkeypatch.setattr(llm_client, "_call_openai_compatible",
                         lambda *a, **k: (_ for _ in ()).throw(TimeoutError("caído también")))

    # No debe lanzar excepción: el pipeline sigue funcionando con el mock.
    result = json.loads(llm_client.call_llm('{"action": ...}', "una formula x=2"))
    assert result["action"] == "render_formula"


def test_circuit_breaker_opens_after_threshold_and_skips_primary(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-primary-fake")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fallback-fake")
    monkeypatch.setenv("LLM_CIRCUIT_FAILURE_THRESHOLD", "2")
    monkeypatch.setenv("LLM_CIRCUIT_RESET_SECONDS", "3600")  # no debe expirar durante el test

    primary_call_count = {"n": 0}

    def failing_primary(sp, ut, api_key, model):
        primary_call_count["n"] += 1
        raise TimeoutError("caído")

    monkeypatch.setattr(llm_client, "_call_anthropic", failing_primary)
    monkeypatch.setattr(llm_client, "_call_openai_compatible",
                         lambda sp, ut, api_key, model, base_url: json.dumps({"from": "fallback"}))

    # 2 fallos = threshold -> breaker abre
    llm_client.call_llm("s", "u")
    llm_client.call_llm("s", "u")
    assert primary_call_count["n"] == 2
    assert llm_client._get_breaker("anthropic_primary").is_open()

    # Tercera llamada: el breaker está abierto, NO debe intentar el primario de nuevo
    llm_client.call_llm("s", "u")
    assert primary_call_count["n"] == 2, "el circuit breaker debe saltarse el proveedor abierto"


def test_circuit_breaker_half_open_retries_after_cooldown(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-primary-fake")
    monkeypatch.setenv("LLM_CIRCUIT_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("LLM_CIRCUIT_RESET_SECONDS", "0")  # cooldown "instantáneo" para el test

    outcomes = iter([TimeoutError("primer intento falla"), None])

    def flaky_primary(sp, ut, api_key, model):
        outcome = next(outcomes)
        if outcome is not None:
            raise outcome
        return json.dumps({"from": "primary_recovered"})

    monkeypatch.setattr(llm_client, "_call_anthropic", flaky_primary)

    # Primer intento: falla, breaker abre (threshold=1)
    first = json.loads(llm_client.call_llm('{"action": ...}', "algo generico"))
    assert first["action"] == "no_action"  # cayó hasta el mock, no hay proveedor de respaldo configurado
    assert llm_client._get_breaker("anthropic_primary").consecutive_failures == 1

    # reset_timeout_seconds=0 -> half-open inmediato, se reintenta el primario y esta vez funciona
    second = json.loads(llm_client.call_llm("s", "u"))
    assert second == {"from": "primary_recovered"}
    assert llm_client._get_breaker("anthropic_primary").consecutive_failures == 0
