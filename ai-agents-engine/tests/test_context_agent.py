import json

from agents import context_agent


def test_invalid_llm_json_preserves_transcript_and_keeps_pipeline_contract(monkeypatch):
    monkeypatch.setattr(
        context_agent,
        "call_llm",
        lambda system_prompt, user_text, **_kwargs: '{"text": "audio final con una comilla',
    )

    chunk = context_agent.extract_semantic_chunk("audio final con una comilla")

    assert chunk.model_dump() == {
        "text": "audio final con una comilla",
        "topic": "general",
        "confidence": 0.3,
    }
