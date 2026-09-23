from __future__ import annotations

from uuid import uuid4

from ..gateway_interface import ChargeRequest, ChargeResult


class PseGateway:
    provider = "pse"

    def charge(self, request: ChargeRequest) -> ChargeResult:
        if request.amount_cents <= 0:
            raise ValueError("Charge amount must be positive")
        if not request.bank_code:
            raise ValueError("PSE requires bank_code")
        return ChargeResult(self.provider, f"PSE-{uuid4().hex}", "pending")

    def refund(self, provider_reference: str, amount_cents: int) -> ChargeResult:
        raise NotImplementedError("PSE refunds require the contracted provider API flow")

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        raise NotImplementedError("PSE webhook signature mechanism requires verified provider documentation")