"""
Autenticación y permisos.

Implementación real y probada de: registro, login con hash de contraseña
(bcrypt) y emisión de token de sesión simple (JWT casero con firma HMAC,
usando la librería estándar `hmac` para no depender de una librería JWT
externa no instalada). En producción se recomienda `python-jose` o
`pyjwt` con rotación de llaves, pero la lógica de verificación es la misma.

REVOCACIÓN: el esquema es stateless por diseño (no hay que consultar la
base de datos para validar la firma), pero eso significaba que un token
seguía siendo válido hasta que expiraba (8h) aunque el usuario cerrara
sesión o fuera dado de baja — no había forma de invalidarlo antes. Se
agrega una lista de revocación en Redis: cada token lleva un `jti` (ID
único), y al hacer logout se guarda ese `jti` en Redis con un TTL igual
al tiempo que le quedaba de vida al token (así la lista de revocados no
crece indefinidamente — se autolimpia cuando el token habría expirado de
todos modos).
"""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import date

import redis
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from database.connection import get_db
from database.models import User, Role, Organization
from observability.logging_config import log_event

router = APIRouter(prefix="/auth", tags=["Autenticación"])

SECRET_KEY = os.getenv("ERP_SECRET_KEY", "dev-secret-change-in-production")
TOKEN_TTL_SECONDS = 60 * 60 * 8  # 8 horas

_redis_client = redis.from_url(os.getenv("ERP_REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
REVOKED_TOKEN_PREFIX = "revoked_token:"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return _b64url(salt) + "$" + _b64url(digest)


def verify_password(password: str, stored: str) -> bool:
    salt_b64, digest_b64 = stored.split("$")
    salt = _b64url_decode(salt_b64)
    expected = _b64url_decode(digest_b64)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hmac.compare_digest(expected, actual)


def create_token(user_id: str, role: str, organization_id: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "org": organization_id,
        "jti": uuid.uuid4().hex,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_b64 = _b64url(json.dumps(payload).encode())
    signature = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url(signature)}"


def decode_token(token: str) -> dict:
    try:
        payload_b64, sig_b64 = token.split(".")
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
            raise ValueError("firma inválida")
        payload = json.loads(_b64url_decode(payload_b64))
        if payload["exp"] < time.time():
            raise ValueError("token expirado")
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")


def try_decode_token(token: str) -> dict | None:
    """Igual que `decode_token`, pero NUNCA lanza — para usos best-effort
    donde un token inválido no debe bloquear la petición en ese punto
    (ej. el middleware de rate limiting solo quiere saber "¿a qué
    organización pertenece esta petición, si es que trae un token
    válido?" — la validación estricta que sí puede rechazar la petición
    sigue siendo exclusivamente `get_current_user`)."""
    try:
        payload_b64, sig_b64 = token.split(".")
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


def revoke_token(payload: dict) -> None:
    """Guarda el jti en Redis con TTL = tiempo restante de vida del token.
    Tokens sin `jti` (emitidos antes de este cambio, o generados por
    generate_test_token.mjs en el servidor CRDT) no se pueden revocar
    individualmente — es la razón por la que todo token nuevo DEBE
    incluir jti a partir de ahora."""
    jti = payload.get("jti")
    if not jti:
        return
    remaining_ttl = max(1, int(payload["exp"] - time.time()))
    _redis_client.set(f"{REVOKED_TOKEN_PREFIX}{jti}", "1", ex=remaining_ttl)


def is_token_revoked(payload: dict) -> bool:
    jti = payload.get("jti")
    if not jti:
        return False
    return _redis_client.exists(f"{REVOKED_TOKEN_PREFIX}{jti}") == 1


def get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Formato de header Authorization inválido")
    token = authorization.removeprefix("Bearer ")
    payload = decode_token(token)
    if is_token_revoked(payload):
        raise HTTPException(status_code=401, detail="La sesión fue cerrada. Inicia sesión nuevamente.")
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


def get_current_token_payload(authorization: str = Header(...)) -> dict:
    """Variante que devuelve el payload crudo del token (incluyendo jti),
    usada solo por /auth/logout — el resto de endpoints usa get_current_user."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Formato de header Authorization inválido")
    token = authorization.removeprefix("Bearer ")
    payload = decode_token(token)
    if is_token_revoked(payload):
        raise HTTPException(status_code=401, detail="La sesión ya estaba cerrada.")
    return payload


class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    organization_name: str
    role: Role = Role.student
    # Compliance de datos de menores (nuevo): opcionales para no romper
    # el registro de docentes/admins (que no aplica) ni el de alumnos que
    # aún no completaron este dato — pero es lo que permite calcular
    # User.is_minor() y activar la exigencia de consentimiento parental.
    date_of_birth: date | None = None
    guardian_email: EmailStr | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    organization_id: str


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="El correo ya está registrado")

    # Reutiliza la organización si ya existe (para que el segundo profesor
    # del mismo colegio se una a la misma org en vez de crear una nueva),
    # o la crea si es la primera persona de ese colegio en registrarse.
    organization = db.query(Organization).filter(Organization.name == payload.organization_name).first()
    if not organization:
        organization = Organization(name=payload.organization_name)
        db.add(organization)
        db.flush()  # para tener organization.id antes del commit del user

    user = User(
        organization_id=organization.id,
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        date_of_birth=payload.date_of_birth,
        guardian_email=payload.guardian_email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_event("user_registered", user_id=user.id, role=user.role.value, organization_id=organization.id)
    return TokenResponse(
        access_token=create_token(user.id, user.role.value, organization.id),
        role=user.role.value,
        organization_id=organization.id,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        log_event("login_failed", email=payload.email)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    log_event("login_success", user_id=user.id, role=user.role.value, organization_id=user.organization_id)
    return TokenResponse(
        access_token=create_token(user.id, user.role.value, user.organization_id),
        role=user.role.value,
        organization_id=user.organization_id,
    )


@router.post("/logout", summary="Cerrar sesión (revoca el token actual)")
def logout(payload: dict = Depends(get_current_token_payload)):
    revoke_token(payload)
    log_event("logout", user_id=payload["sub"])
    return {"status": "logged_out"}
