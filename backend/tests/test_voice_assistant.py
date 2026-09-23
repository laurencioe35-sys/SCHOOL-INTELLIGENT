import pytest

from app.modules.voice_assistant.assistant import answer_account_balance
from app.modules.voice_assistant.confidential_guard.permission_check import VoiceAccessDenied, check_screen_permission
from app.modules.voice_assistant.confidential_guard.redaction_rules import redact_voice_fields


def test_voice_channel_cannot_bypass_screen_restriction():
    with pytest.raises(VoiceAccessDenied):
        answer_account_balance(role="teacher", account_code="1105", load_balance=lambda _: {"balance": 100})


def test_blocked_account_number_is_redacted_even_with_screen_permission():
    check_screen_permission(role="admin", resource="account_balance")
    response = answer_account_balance(
        role="admin",
        account_code="1105",
        load_balance=lambda _: {"balance": 100, "account_number": "4111111111111111"},
    )
    assert response.data == {"balance": 100, "account_number": "[REDACTED]"}


def test_unknown_balance_is_not_invented():
    response = answer_account_balance(role="admin", account_code="9999", load_balance=lambda _: {})
    assert response.data is None
    assert "No puedo" in response.text