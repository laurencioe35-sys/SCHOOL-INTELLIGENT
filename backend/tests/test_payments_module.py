import hashlib
import hmac

from app.modules.payments.gateway_interface import ChargeRequest
from app.modules.payments.idempotency_store import IdempotencyStore
from app.modules.payments.providers.stripe import StripeGateway
from app.modules.payments.reconciliation.matcher import PaymentRecord, reconcile_payment


def test_stripe_verifies_signature_and_rejects_raw_card_number():
    gateway = StripeGateway("secret")
    payload = b'{"type":"payment_succeeded"}'
    signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()

    assert gateway.verify_webhook_signature(payload, signature)
    try:
        gateway.charge(ChargeRequest(1000, "COP", "4242424242424242", "key-1"))
    except ValueError as error:
        assert "tokenized" in str(error)
    else:
        raise AssertionError("raw card numbers must be rejected")


def test_reconciliation_covers_duplicate_partial_overpayment_and_currency():
    payment = PaymentRecord("ch_1", 500, "COP", ("inv-1",))
    assert reconcile_payment(payment, 1000, "COP").status == "partially_paid"
    assert reconcile_payment(payment, 400, "COP").status == "overpayment"
    assert reconcile_payment(payment, 500, "USD").status == "currency_mismatch"
    assert reconcile_payment(payment, 500, "COP", already_reconciled=True).status == "duplicate"


def test_idempotency_store_expires_values():
    now = [100.0]
    store = IdempotencyStore(ttl_seconds=10, clock=lambda: now[0])
    store.put("evt-1", "processed")
    assert store.get("evt-1") == "processed"
    now[0] = 111.0
    assert store.get("evt-1") is None