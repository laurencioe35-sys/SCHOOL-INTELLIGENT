from __future__ import annotations

from uuid import uuid4

from ..gateway_interface import ChargeRequest, ChargeResult


class NequiGateway:
    provider = "nequi"

    def charge(self, request: ChargeRequest) -> ChargeResult:
        if request.amount_cents <= 0:
            raise ValueError("Charge amount must be positive")
        return ChargeResult(self.provider, f"NEQ-{uuid4().hex}", "pending")

    def refund(self, provider_reference: str, amount_cents: int) -> ChargeResult:
        raise NotImplementedError("Nequi refunds require the contracted provider API flow")

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        raise NotImplementedError("Nequi webhook signature mechanism requires verified provider documentation")