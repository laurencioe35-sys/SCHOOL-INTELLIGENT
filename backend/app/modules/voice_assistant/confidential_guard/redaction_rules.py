from __future__ import annotations

from typing import Any


VOICE_FIELD_RULES = {
    "account_number": "BLOCK",
    "net_salary": "CONFIRMATION_REQUIRED",
}


def redact_voice_fields(payload: dict[str, Any], *, confirmed_fields: set[str] | None = None) -> dict[str, Any]:
    confirmed = confirmed_fields or set()
    redacted = dict(payload)
    for field, rule in VOICE_FIELD_RULES.items():
        if field not in redacted:
            continue
        if rule == "BLOCK" or (rule == "CONFIRMATION_REQUIRED" and field not in confirmed):
            redacted[field] = "[REDACTED]"
    return redacted