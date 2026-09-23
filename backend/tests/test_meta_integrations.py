from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet

from app.modules.integrations_social.meta_webhooks.idempotency_store import MetaIdempotencyStore
from app.modules.integrations_social.meta_webhooks.signature_verifier import verify_signature
from app.modules.integrations_social.token_vault import TokenVault
from app.modules.integrations_social.whatsapp.client import WhatsAppClient
from app.modules.integrations_social.whatsapp.opt_in_registry import OptInRegistry, OptInRequiredError
from app.modules.integrations_social.whatsapp.templates_registry import TemplateRegistry


def test_meta_signature_and_idempotency():
    assert verify_signature(b"event", "sha256=bad", "secret") is False
    store = MetaIdempotencyStore()
    assert store.claim("event-1") is True
    assert store.claim("event-1") is False


def test_token_vault_never_exposes_plaintext_repr():
    key = Fernet.generate_key()
    sealed = TokenVault(key).seal("secret-token")
    assert "secret-token" not in repr(sealed)
    assert sealed.reveal(key) == "secret-token"


def test_whatsapp_opt_in_and_unapproved_template_do_not_send():
    opt_ins, templates = OptInRegistry(), TemplateRegistry()
    client = WhatsAppClient(opt_ins, templates)
    templates.register_placeholder("invoice_notification")
    with pytest.raises(OptInRequiredError):
        client.send_template("573001234567", "invoice_notification", datetime.now(UTC))
    opt_ins.register("573001234567")
    result = client.send_template("573001234567", "invoice_notification", datetime.now(UTC))
    assert result.sent is False
    assert "not approved" in result.reason