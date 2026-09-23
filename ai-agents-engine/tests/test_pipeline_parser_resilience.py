from agents import context_agent, pedagogical_agent, ui_compiler_agent


def test_core_agents_keep_valid_contracts_when_llm_returns_truncated_json(monkeypatch):
    monkeypatch.setattr(context_agent, "call_llm", lambda *_, **__: '{"text": "clase')
    monkeypatch.setattr(pedagogical_agent, "call_llm", lambda *_, **__: '{"action": "render')
    monkeypatch.setattr(ui_compiler_agent, "call_llm", lambda *_, **__: '{"component_type": "object')

    chunk = context_agent.extract_semantic_chunk("Hoy estudiamos el volumen de un poliedro")
    decision = pedagogical_agent.decide_pedagogical_action(chunk)
    component = ui_compiler_agent.compile_ui_component(chunk.text, decision, "session-parser")

    assert chunk.text.startswith("Hoy estudiamos")
    assert decision.action == "render_3d_object"
    assert component is not None
    assert component.component_type == "object3d"
    assert component.session_id == "session-parser"


def test_ui_compiler_replaces_empty_gemini_payload_with_safe_component(monkeypatch):
    monkeypatch.setattr(
        ui_compiler_agent,
        "call_llm",
        lambda *_, **__: '{"component_type": "formula", "payload": {}}',
    )
    decision = ui_compiler_agent.PedagogicalDecision(
        action="render_formula",
        reason="Gemini pidió una fórmula.",
        priority="medium",
    )

    component = ui_compiler_agent.compile_ui_component("V = a³", decision, "session-empty-payload")

    assert component is not None
    assert component.component_type == "formula"
    assert component.payload == {"text": "V = a³"}
