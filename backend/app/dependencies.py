from uuid import UUID
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from .db import get_db
from .security import current_claims

def tenant_context(claims: dict = Depends(current_claims)) -> UUID:
    try:
        return UUID(claims["tenant_id"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid tenant context") from exc

def require_roles(*roles: str):
    def dependency(claims: dict = Depends(current_claims)) -> dict:
        if claims.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return claims
    return dependency

DB = Depends(get_db)
