from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentRecord:
    provider_reference: str
    amount_cents: int
    currency: str
    invoice_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    reason: str
    applied_amount_cents: int = 0


def reconcile_payment(
    payment: PaymentRecord,
    invoice_amount_cents: int,
    invoice_currency: str,
    *,
    already_reconciled: bool = False,
    payment_status: str = "succeeded",
) -> ReconciliationResult:
    if payment_status == "pending":
        return ReconciliationResult("pending", "Payment is awaiting asynchronous provider confirmation")
    if already_reconciled:
        return ReconciliationResult("duplicate", "Payment provider reference was already reconciled")
    if len(payment.invoice_ids) != 1:
        status = "multi_invoice" if len(payment.invoice_ids) > 1 else "unmatched"
        return ReconciliationResult(status, "Payment must reference exactly one invoice")
    if payment.currency != invoice_currency:
        return ReconciliationResult("currency_mismatch", "Payment and invoice currencies differ")
    if payment.amount_cents <= 0:
        return ReconciliationResult("invalid", "Payment amount must be positive")
    if payment.amount_cents > invoice_amount_cents:
        return ReconciliationResult("overpayment", "Payment exceeds invoice balance")
    if payment.amount_cents < invoice_amount_cents:
        return ReconciliationResult("partially_paid", "Payment applied partially to invoice", payment.amount_cents)
    return ReconciliationResult("paid", "Payment fully reconciled with invoice", payment.amount_cents)