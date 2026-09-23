from __future__ import annotations

import hashlib
import hmac
from uuid import uuid4

from ..gateway_interface import ChargeRequest, ChargeResult


class StripeGateway:
    def __init__(self, webhook_secret: str) -> None:
        self.webhook_secret = webhook_secret.encode()

    def charge(self, request: ChargeRequest) -> ChargeResult:
        if request.amount_cents <= 0:
            raise ValueError("Charge amount must be positive")
        if not request.payment_token or request.payment_token.isdigit() and len(request.payment_token) >= 12:
            raise ValueError("Use a tokenized payment method")
        return ChargeResult("stripe", f"ch_{uuid4().hex}", "succeeded")

    def refund(self, provider_reference: str, amount_cents: int) -> ChargeResult:
        if amount_cents <= 0:
            raise ValueError("Refund amount must be positive")
        return ChargeResult("stripe", f"re_{uuid4().hex}", "refunded")

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(self.webhook_secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)