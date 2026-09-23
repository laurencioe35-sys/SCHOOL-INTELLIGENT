import pytest

from app.academic_memory import fingerprint, validate


def valid_payload(**overrides):
    payload = {
        "academic": True,
        "subject": "Mathematics",
        "grade": "9",
        "topic": "Quadratic equations",
        "content_type": "SOLVED_EXERCISE",
        "title": "Factoring a quadratic",
        "content": "Factor x squared minus five x plus six.",
        "steps": ["Find factors", "Solve each factor"],
        "answer": "x equals 2 or 3",
        "keywords": ["quadratic", "factoring"],
        "language": "en",
    }
    payload.update(overrides)
    return payload


def test_academic_gate_accepts_structured_reusable_knowledge():
    content = validate(valid_payload())
    assert content.content_type == "SOLVED_EXERCISE"
    assert content.keywords == ["quadratic", "factoring"]


@pytest.mark.parametrize("payload", [
    valid_payload(academic=False),
    valid_payload(content_type="CHAT"),
    valid_payload(content="api_key=must-not-be-stored"),
    valid_payload(steps=["", "valid step"]),
])
def test_academic_gate_rejects_non_reusable_or_sensitive_content(payload):
    with pytest.raises(ValueError):
        validate(payload)


def test_fingerprint_is_stable_for_equivalent_content():
    assert fingerprint(validate(valid_payload(content="  Factor X SQUARED minus five x plus six.  "))) == fingerprint(validate(valid_payload()))
