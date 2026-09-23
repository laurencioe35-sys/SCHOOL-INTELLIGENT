from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class CanonicalPaymentWebhook:
    """Provider-neutral event accepted after signature verification."""

    provider: str
    provider_event_id: str
    provider_reference: str
    tenant_id: UUID
    invoice_id: UUID
    status: str
    amount_cents: int
    currency: str
    occurred_at: datetime

    def validate_transition(self) -> None:
        if not self.provider or not self.provider_event_id or not self.provider_reference:
            raise ValueError("Provider event identity is required")
        if self.status not in {"pending", "paid", "failed", "expired", "refunded"}:
            raise ValueError("Unsupported payment status")
        if self.amount_cents <= 0:
            raise ValueError("Payment amount must be positive")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("Currency must be an ISO-4217 code")
