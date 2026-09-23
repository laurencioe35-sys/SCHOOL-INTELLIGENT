from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from threading import Lock

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.db import clear_current_tenant_id, set_current_tenant_id


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Populate the tenant context used by database and audit operations."""

    async def dispatch(self, request: Request, call_next):
        tenant_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
                tenant_id = claims.get("tenant_id")
            except jwt.PyJWTError:
                tenant_id = None

        request.state.tenant_id = tenant_id
        set_current_tenant_id(tenant_id)
        try:
            return await call_next(request)
        finally:
            clear_current_tenant_id()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Basic tenant/IP rate limiting for production hardening.

    This middleware deliberately fails open if the feature is disabled, keeping
    the service available while still allowing opt-in protection in production.
    """

    _buckets: dict[str, list[float]] = defaultdict(list)
    _lock = Lock()
    _redis_clients = {}

    @staticmethod
    def _tenant_id_from_request(request: Request) -> str | None:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return getattr(request.state, "tenant_id", None)
        token = auth_header.split(" ", 1)[1].strip()
        try:
            claims = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return getattr(request.state, "tenant_id", None)
        return claims.get("tenant_id")

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return await call_next(request)

        now = time.time()
        window = settings.rate_limit_window_seconds
        tenant_id = self._tenant_id_from_request(request)
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        def _memory_bucket_for(limit: int, key: str) -> bool:
            if limit <= 0:
                return False
            with self._lock:
                bucket = self._buckets[key]
                cutoff = now - window
                bucket[:] = [stamp for stamp in bucket if stamp > cutoff]
                if len(bucket) >= limit:
                    return True
                bucket.append(now)
                return False

        async def _bucket_for(limit: int, key: str) -> bool:
            if limit <= 0:
                return False
            if not settings.redis_url:
                return _memory_bucket_for(limit, key)

            try:
                import redis

                client = self._redis_clients.get(settings.redis_url)
                if client is None:
                    client = redis.Redis.from_url(settings.redis_url)
                    self._redis_clients[settings.redis_url] = client
                bucket = f"rate-limit:{key}:{int(now // window)}"
                count = await asyncio.to_thread(client.incr, bucket)
                if count == 1:
                    await asyncio.to_thread(client.expire, bucket, window + 1)
                return count > limit
            except Exception:
                return _memory_bucket_for(limit, key)

        if path.startswith("/api/v1/auth/"):
            should_block = await _bucket_for(settings.rate_limit_auth_per_ip_per_minute, f"auth_ip:{client_ip}")
            if should_block:
                return JSONResponse({"detail": "Too many login attempts. Try again later."}, status_code=429, headers={"Retry-After": str(window)})
        if tenant_id:
            should_block = await _bucket_for(settings.rate_limit_per_tenant_per_minute, f"tenant:{tenant_id}")
            if should_block:
                return JSONResponse({"detail": "Tenant peak exceeded. Please retry later."}, status_code=429, headers={"Retry-After": str(window)})
        should_block = await _bucket_for(settings.rate_limit_per_ip_per_minute, f"ip:{client_ip}")
        if should_block:
            return JSONResponse({"detail": "Request rate limit exceeded."}, status_code=429, headers={"Retry-After": str(window)})

        return await call_next(request)
