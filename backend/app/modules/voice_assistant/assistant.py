from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .confidential_guard.permission_check import check_screen_permission
from .confidential_guard.redaction_rules import redact_voice_fields


@dataclass(frozen=True)
class VoiceResponse:
    text: str
    data: dict[str, object] | None
    audited: bool


def answer_account_balance(
    *, role: str, account_code: str, load_balance: Callable[[str], dict[str, object]]
) -> VoiceResponse:
    check_screen_permission(role=role, resource="account_balance")
    record = load_balance(account_code)
    if not record:
        return VoiceResponse("No puedo consultar ese saldo con los datos disponibles.", None, True)
    return VoiceResponse(
        f"El saldo de la cuenta {account_code} está disponible.",
        redact_voice_fields(record),
        True,
    )