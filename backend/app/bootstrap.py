from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select

from .db import SessionLocal
from .models import Tenant, User
from .security import hash_password

DEFAULT_TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")
DEFAULT_TENANT_NAME = "ERP Educativo Demo"
DEFAULT_ADMIN_EMAIL = "admin@demo.erp"
DEFAULT_ADMIN_PASSWORD = "Demo123!"


def ensure_default_bootstrap() -> None:
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.id == DEFAULT_TENANT_ID))
        if tenant is None:
            db.add(Tenant(id=DEFAULT_TENANT_ID, name=DEFAULT_TENANT_NAME, active=True))

        user = db.scalar(
            select(User).where(
                User.tenant_id == DEFAULT_TENANT_ID,
                User.email == DEFAULT_ADMIN_EMAIL,
            )
        )
        if user is None:
            db.add(
                User(
                    id=uuid4(),
                    tenant_id=DEFAULT_TENANT_ID,
                    email=DEFAULT_ADMIN_EMAIL,
                    password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
                    role="admin",
                    active=True,
                )
            )
        else:
            user.password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
            user.role = "admin"
            user.active = True

        db.commit()
