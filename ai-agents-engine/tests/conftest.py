import pytest


@pytest.fixture(autouse=True)
def allow_deterministic_llm_only_in_tests(monkeypatch):
    monkeypatch.setenv("LLM_ALLOW_MOCK", "true")
