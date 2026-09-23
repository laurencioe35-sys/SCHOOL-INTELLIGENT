import pytest

from run_service import build_production_loop


def test_production_worker_requires_redis(monkeypatch):
    monkeypatch.delenv("ERP_REDIS_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "configured-for-test")

    with pytest.raises(RuntimeError, match="ERP_REDIS_URL"):
        build_production_loop()


def test_production_worker_requires_real_llm(monkeypatch):
    monkeypatch.setenv("ERP_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr("run_service._require_redis_dependency", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_FALLBACK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_ALLOW_MOCK", raising=False)

    with pytest.raises(RuntimeError, match="real LLM"):
        build_production_loop()


def test_production_worker_builds_real_stream_loop(monkeypatch):
    monkeypatch.setenv("ERP_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")

    try:
        loop = build_production_loop()
    except RuntimeError as error:
        assert "redis Python package" in str(error)
    else:
        assert loop.event_queue._stream == "class:transcript:chunks"
        assert loop.output_queue._stream == "class:agent:results"