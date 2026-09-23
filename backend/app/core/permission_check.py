from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog


def _enforce_segregation_of_duties(
    db: Session,
    *,
    tenant_id: UUID | str,
    actor_user_id: UUID | str,
    entity_name: str,
    entity_id: str,
    action: str,
) -> None:
    """Ensure a creator of an entity cannot approve it in the same tenant.

    The check is based on the real audit log, not the declared role, matching the
    security model described in the prompt files.
    """
    if action.upper() not in {"APPROVE", "PAY"}:
        return
    prior = db.scalar(
        select(AuditLog).where(
            AuditLog.tenant_id == UUID(str(tenant_id)),
            AuditLog.actor_user_id == UUID(str(actor_user_id)),
            AuditLog.entity_name == entity_name,
            AuditLog.entity_id == entity_id,
            AuditLog.action.in_({"CREATE", "INITIATE"}),
        )
    )
    if prior is not None:
        raise PermissionError("Segregation of duties violation: actor cannot approve their own record")
