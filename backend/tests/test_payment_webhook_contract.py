from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.payments.webhook_contract import CanonicalPaymentWebhook


def test_canonical_payment_webhook_accepts_verified_internal_event():
    event = CanonicalPaymentWebhook(
        provider="nequi",
        provider_event_id="evt-1",
        provider_reference="NEQ-1",
        tenant_id=uuid4(),
        invoice_id=uuid4(),
        status="paid",
        amount_cents=1000,
        currency="COP",
        occurred_at=datetime.now(UTC),
    )

    event.validate_transition()


@pytest.mark.parametrize("status", ["unknown", "settled"])
def test_canonical_payment_webhook_rejects_unknown_status(status):
    event = CanonicalPaymentWebhook(
        provider="pse",
        provider_event_id="evt-1",
        provider_reference="PSE-1",
        tenant_id=uuid4(),
        invoice_id=uuid4(),
        status=status,
        amount_cents=1000,
        currency="COP",
        occurred_at=datetime.now(UTC),
    )

    with pytest.raises(ValueError, match="Unsupported payment status"):
        event.validate_transition()
