from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChargeRequest:
    amount_cents: int
    currency: str
    payment_token: str
    idempotency_key: str
    bank_code: str | None = None


@dataclass(frozen=True)
class ChargeResult:
    provider: str
    provider_reference: str
    status: str


class PaymentGateway(Protocol):
    def charge(self, request: ChargeRequest) -> ChargeResult: ...

    def refund(self, provider_reference: str, amount_cents: int) -> ChargeResult: ...

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool: ...