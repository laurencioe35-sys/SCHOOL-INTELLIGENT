"""
Facturación / pensiones.

TRANSPARENCIA sobre el pago: este módulo simula una pasarela de pago
(similar a como se hizo con el LLM mock en ai-agents-engine) SOLO cuando
no hay credenciales configuradas. La estructura del código separa
claramente:
  1) La lógica de negocio (crear factura, marcarla como pagada, historial)
     — esto SÍ es real y probado.
  2) El punto de integración con la pasarela (`_charge_with_payment_gateway`)
     — con `PAYMENT_GATEWAY_API_KEY` configurada y `PAYMENT_GATEWAY_PROVIDER=stripe`
     (el valor por defecto), esto llama de verdad a la API de Stripe con
     el SDK oficial. Sin la key (como en este entorno de desarrollo), cae
     al mock explícito de siempre.

IMPORTANTE — por qué Stripe y no Culqi/Niubiz para el cobro real: Stripe
tiene un SDK oficial instalable (`pip install stripe`) que sí se pudo
instalar y ejercitar en este entorno (ver tests/test_billing_stripe.py,
que mockea la llamada de red — no hay credenciales reales de una cuenta
de comercio, así que no se hizo un cargo real). PERO Stripe NO soporta
PEN (sol peruano) como moneda de liquidación — ver
https://docs.stripe.com/currencies para la lista vigente. Para cobrar en
PEN de verdad (el caso de uso real de este ERP, pensiones en Perú) hace
falta Culqi o Niubiz, que si soportan PEN nativamente pero requieren una
cuenta de comercio verificada con RUC que no existe en este entorno de
desarrollo — por eso siguen documentados como mock más abajo, exactamente
igual que antes. Si la organización cobra en USD (ej. programas
internacionales), la integración de Stripe de este archivo ya es
funcional con solo configurar la API key real.
"""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from database.connection import get_db
from database.models import User, Role, Invoice, InvoiceStatus
from api.auth import get_current_user
from observability.logging_config import log_event

router = APIRouter(prefix="/billing", tags=["Facturación / Pensiones"])

PAYMENT_GATEWAY_API_KEY = os.getenv("PAYMENT_GATEWAY_API_KEY", "")
PAYMENT_GATEWAY_PROVIDER = os.getenv("PAYMENT_GATEWAY_PROVIDER", "stripe").lower()
USE_REAL_PAYMENT_GATEWAY = bool(PAYMENT_GATEWAY_API_KEY)

# Monedas que Stripe NO soporta como moneda de liquidación/cobro (lista no
# exhaustiva; PEN es el caso relevante para este ERP). Si se intenta
# cobrar en una de estas con el proveedor Stripe, se rechaza explícito en
# vez de dejar que Stripe devuelva un error críptico de moneda inválida.
_STRIPE_UNSUPPORTED_CURRENCIES = {"pen"}


class InvoiceCreate(BaseModel):
    student_id: str
    concept: str
    amount_cents: float
    currency: str = "PEN"
    due_date: datetime


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    concept: str
    amount_cents: float
    currency: str
    status: str
    due_date: datetime
    paid_at: datetime | None
    payment_reference: str | None


class PayInvoiceRequest(BaseModel):
    payment_method_token: str  # token de tarjeta que entregaría el SDK de la pasarela real


def _charge_with_stripe(amount_cents: float, currency: str, payment_method_token: str) -> dict:
    """Cargo real con el SDK oficial de Stripe.

    `payment_method_token` debe ser un PaymentMethod id (ej. "pm_...")
    generado en el cliente con Stripe.js/Stripe SDK móvil — nunca un
    número de tarjeta crudo, que este backend no debe tocar (alcance de
    PCI-DSS). Se usa `confirm=True` con `off_session=False` porque el
    flujo esperado aquí es un cobro iniciado por el propio pagador (el
    apoderado pagando la pensión), no un cargo recurrente automático.
    """
    import stripe

    stripe.api_key = PAYMENT_GATEWAY_API_KEY

    try:
        intent = stripe.PaymentIntent.create(
            amount=int(round(amount_cents)),
            currency=currency.lower(),
            payment_method=payment_method_token,
            confirm=True,
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
        )
    except stripe.error.CardError as exc:
        # Rechazo de tarjeta (fondos insuficientes, tarjeta vencida, etc.):
        # esto es un resultado de negocio normal, no una excepción no
        # manejada — se traduce a la misma forma de respuesta que el mock.
        return {"success": False, "reference": None, "gateway": "stripe", "decline_reason": exc.user_message}
    except stripe.error.StripeError as exc:
        # Errores de configuración/red/API sí deben verse como fallo del
        # sistema (401 de la API, timeout, etc.), no como un rechazo de
        # tarjeta silencioso.
        raise HTTPException(status_code=502, detail=f"Error comunicándose con la pasarela de pago: {exc.user_message or str(exc)}")

    success = intent.status == "succeeded"
    return {"success": success, "reference": intent.id, "gateway": "stripe", "status": intent.status}


def _charge_with_payment_gateway(amount_cents: float, currency: str, payment_method_token: str) -> dict:
    """Punto de integración con la pasarela de pago real.

    Si PAYMENT_GATEWAY_API_KEY está configurada, delega al proveedor real
    (Stripe por defecto — ver `_charge_with_stripe`). Sin esa key (como en
    este entorno), se simula un cobro exitoso determinístico para poder
    probar el flujo de negocio completo.
    """
    if USE_REAL_PAYMENT_GATEWAY:
        if PAYMENT_GATEWAY_PROVIDER == "stripe":
            if currency.lower() in _STRIPE_UNSUPPORTED_CURRENCIES:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Stripe no soporta cobros en {currency.upper()}. "
                        "Usa Culqi o Niubiz para pensiones en soles, o cobra en una "
                        "moneda soportada por Stripe (ver https://docs.stripe.com/currencies)."
                    ),
                )
            return _charge_with_stripe(amount_cents, currency, payment_method_token)
        raise NotImplementedError(
            f"PAYMENT_GATEWAY_PROVIDER='{PAYMENT_GATEWAY_PROVIDER}' no implementado. "
            "Proveedores soportados: 'stripe'. Para Culqi/Niubiz/MercadoPago, agregar "
            "aquí la llamada HTTP real siguiendo el mismo contrato de retorno."
        )
    return {
        "success": True,
        "reference": f"MOCK-{uuid.uuid4().hex[:12]}",
        "gateway": "mock",
    }


def _require_teacher_or_admin(user: User):
    if user.role not in (Role.teacher, Role.admin):
        raise HTTPException(status_code=403, detail="Solo docentes o administradores pueden gestionar facturación")


@router.post("/invoices", response_model=InvoiceOut, summary="Generar una pensión/cobro para un alumno")
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_teacher_or_admin(user)

    student = (
        db.query(User)
        .filter(User.id == payload.student_id, User.organization_id == user.organization_id, User.role == Role.student)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Alumno no encontrado en esta organización")

    invoice = Invoice(
        organization_id=user.organization_id,
        student_id=student.id,
        concept=payload.concept,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        due_date=payload.due_date,
        status=InvoiceStatus.pending,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    log_event("invoice_created", invoice_id=invoice.id, student_id=student.id, amount_cents=payload.amount_cents)
    return invoice


@router.get("/invoices/student/{student_id}", response_model=list[InvoiceOut], summary="Ver pensiones de un alumno")
def list_student_invoices(student_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == Role.student and user.id != student_id:
        raise HTTPException(status_code=403, detail="No puedes ver las pensiones de otro alumno")

    return (
        db.query(Invoice)
        .filter(Invoice.student_id == student_id, Invoice.organization_id == user.organization_id)
        .order_by(Invoice.due_date.desc())
        .all()
    )


@router.post("/invoices/{invoice_id}/pay", response_model=InvoiceOut, summary="Pagar una pensión")
def pay_invoice(invoice_id: str, payload: PayInvoiceRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.organization_id == user.organization_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    # Un alumno solo puede pagar SU propia factura; un docente/admin puede
    # pagar (o registrar el pago de) cualquier factura de su organización.
    if user.role == Role.student and user.id != invoice.student_id:
        raise HTTPException(status_code=403, detail="No puedes pagar la factura de otro alumno")

    if invoice.status == InvoiceStatus.paid:
        raise HTTPException(status_code=400, detail="Esta factura ya fue pagada")

    result = _charge_with_payment_gateway(invoice.amount_cents, invoice.currency, payload.payment_method_token)
    if not result["success"]:
        log_event("invoice_payment_failed", invoice_id=invoice.id)
        raise HTTPException(status_code=402, detail="El pago fue rechazado por la pasarela")

    invoice.status = InvoiceStatus.paid
    invoice.paid_at = datetime.now(timezone.utc)
    invoice.payment_reference = result["reference"]
    db.commit()
    db.refresh(invoice)
    log_event("invoice_paid", invoice_id=invoice.id, student_id=invoice.student_id, reference=result["reference"])
    return invoice


@router.get("/invoices/overdue", response_model=list[InvoiceOut], summary="Listar pensiones vencidas de la organización")
def list_overdue_invoices(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_teacher_or_admin(user)
    now = datetime.now(timezone.utc)
    overdue = (
        db.query(Invoice)
        .filter(
            Invoice.organization_id == user.organization_id,
            Invoice.status == InvoiceStatus.pending,
            Invoice.due_date < now,
        )
        .all()
    )
    # Actualiza el estado a "overdue" al consultarlas — en producción esto
    # sería un job periódico (similar al batch worker), no solo al consultar.
    for inv in overdue:
        inv.status = InvoiceStatus.overdue
    if overdue:
        db.commit()
    return overdue
