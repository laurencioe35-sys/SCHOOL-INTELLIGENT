import pytest

from app.modules.payments.gateway_interface import ChargeRequest
from app.modules.payments.providers.nequi import NequiGateway
from app.modules.payments.providers.pse import PseGateway
from app.modules.payments.reconciliation.matcher import PaymentRecord, reconcile_payment


def test_nequi_charge_is_pending_until_webhook_confirmation():
    result = NequiGateway().charge(ChargeRequest(1000, "COP", "wallet-user", "evt-1"))
    assert result.status == "pending"
    assert reconcile_payment(
        PaymentRecord(result.provider_reference, 1000, "COP", ("invoice-1",)),
        1000,
        "COP",
        payment_status=result.status,
    ).status == "pending"


def test_pse_requires_bank_and_starts_pending():
    gateway = PseGateway()
    with pytest.raises(ValueError):
        gateway.charge(ChargeRequest(1000, "COP", "account-ref", "evt-2"))
    result = gateway.charge(
        ChargeRequest(1000, "COP", "account-ref", "evt-2", bank_code="bank-001")
    )
    assert result.status == "pending"


def test_unknown_provider_webhook_signature_is_not_falsely_verified():
    with pytest.raises(NotImplementedError):
        NequiGateway().verify_webhook_signature(b"payload", "signature")
    with pytest.raises(NotImplementedError):
        PseGateway().verify_webhook_signature(b"payload", "signature")
