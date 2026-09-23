from agents_v2.teacher_response_agent import TeacherResponseAgent
from orchestrator.blackboard import InMemoryBlackboard


def test_teacher_response_agent_publishes_validated_message(monkeypatch):
    monkeypatch.setattr(
        "agents_v2.teacher_response_agent.call_llm",
        lambda *_args, **_kwargs: '{"message": "El binomio al cuadrado se desarrolla como a² + 2ab + b²."}',
    )
    blackboard = InMemoryBlackboard()
    blackboard.set("class-1", "last_topic", "binomios")

    response = TeacherResponseAgent().handle(
        {"type": "transcript_chunk", "session_id": "class-1", "raw_text": "Explica el binomio al cuadrado"},
        blackboard,
    )

    assert response.message == "El binomio al cuadrado se desarrolla como a² + 2ab + b²."
    assert response.topic == "binomios"
    assert blackboard.get("class-1", "teacher_responses")[0]["message"] == response.message


def test_teacher_response_agent_returns_a_board_ready_formula(monkeypatch):
    monkeypatch.setattr(
        "agents_v2.teacher_response_agent.call_llm",
        lambda *_args, **_kwargs: '''{
            "message": "Ejemplo resuelto de binomio al cuadrado.",
            "destination": "board",
            "component": {
                "component_type": "formula",
                "payload": {"text": "(a+b)^2 = a^2 + 2ab + b^2"}
            }
        }''',
    )
    response = TeacherResponseAgent().handle(
        {"type": "transcript_chunk", "session_id": "class-1", "raw_text": "Ejemplo de binomios"},
        InMemoryBlackboard(),
    )

    assert response.destination == "board"
    assert response.component is not None
    assert response.component.component_type == "formula"
    assert response.component.session_id == "class-1"
