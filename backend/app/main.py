from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .bootstrap import ensure_default_bootstrap
from .config import get_settings
from .core.middleware import RateLimitMiddleware, TenantContextMiddleware
from .db import Base, engine, initialize_db
from .migrations import SCHEMA_VERSION, current_version
from .modules.accounting.routes import router as accounting_router
from .academic_routes import router as academic_memory_router
from .routes import router

settings = get_settings()
settings.validate_production_settings()
initialize_db()
ensure_default_bootstrap()

app = FastAPI(title="ERP Educativo Enterprise API", version="0.1.0")
app.add_middleware(TenantContextMiddleware)
app.add_middleware(RateLimitMiddleware)
# Middleware is executed in reverse registration order. Keep CORS outermost so
# browsers can read rate-limit and other middleware-generated error responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(academic_memory_router)
app.include_router(accounting_router)


@app.get("/")
def root() -> dict:
    return {"name": "ERP Educativo Enterprise", "version": app.version}


@app.get("/readiness")
def readiness() -> dict:
    blockers = settings.production_blockers if settings.environment == "production" else []
    database_ok = True
    database_error = None
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception as error:
        database_ok = False
        database_error = str(error)
    schema_version = current_version(engine)
    if not database_ok:
        blockers.append("Database connectivity failed")
    if schema_version < SCHEMA_VERSION:
        blockers.append(f"Database schema is behind: {schema_version}/{SCHEMA_VERSION}")
    return {
        "ready": not blockers,
        "environment": settings.environment,
        "database_ok": database_ok,
        "database_error": database_error,
        "schema_version": schema_version,
        "required_schema_version": SCHEMA_VERSION,
        "blockers": blockers,
    }
