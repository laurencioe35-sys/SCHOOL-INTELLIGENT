"""
Facturación / pensiones.

TRANSPARENCIA sobre el pago: este módulo simula una pasarela de pago
(similar a como se hizo con el LLM mock en ai-agents-engine). El motivo es
el mismo: integrar una pasarela real (Culqi, Niubiz, MercadoPago — las más
usadas en Perú) requiere credenciales de una cuenta de comercio real que
no existen en este entorno de desarrollo. La estructura del código separa
claramente:
  1) La lógica de negocio (crear factura, marcarla como pagada, historial)
     — esto SÍ es real y probado.
  2) El punto de integración con la pasarela (`_charge_with_payment_gateway`)
     — esto es un mock explícito, con la firma exacta que tendría la
     llamada real, para que conectar Culqi/Niubiz después sea cambiar
     una función, no rediseñar el módulo.
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

USE_REAL_PAYMENT_GATEWAY = bool(os.getenv("PAYMENT_GATEWAY_API_KEY"))


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


def _charge_with_payment_gateway(amount_cents: float, currency: str, payment_method_token: str) -> dict:
    """Punto de integración con la pasarela de pago real.

    Si PAYMENT_GATEWAY_API_KEY está configurada, aquí iría la llamada real
    (ej. a la API de Culqi: POST /v2/charges con el token de la tarjeta).
    Sin esa key (como en este entorno), se simula un cobro exitoso
    determinístico para poder probar el flujo de negocio completo.
    """
    if USE_REAL_PAYMENT_GATEWAY:
        raise NotImplementedError(
            "Integración real de pasarela de pago no implementada en este MVP. "
            "Agregar aquí la llamada HTTP real a Culqi/Niubiz/MercadoPago."
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
