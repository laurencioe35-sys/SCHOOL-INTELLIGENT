"""
Rate limiting por tenant/IP — NUEVO, no existía en el proyecto.

PROBLEMA REAL: con multi-tenancy ya construido (varios colegios
comparten el mismo backend), un solo tenant con un bug en su
integración (o un actor malicioso) podía saturar CPU/DB para TODOS los
demás tenants — no había ningún límite de tasa en `requirements.txt` ni
en `main.py`. Tampoco había protección de fuerza bruta en
`/auth/login`: un atacante podía probar contraseñas sin límite alguno.

DISEÑO: contador de ventana fija en Redis (`INCR` + `EXPIRE`). Es más
simple que un sliding window log o un token bucket, y su compromiso
conocido (un cliente puede hacer hasta ~2x el límite si concentra
tráfico justo en el borde entre dos ventanas) es aceptable para el
objetivo real — contener abuso y fuerza bruta, no facturar con
precisión de milisegundo. Se documenta aquí a propósito, en vez de
ocultarlo detrás de "rate limiting" como si fuera perfecto.

FAIL-OPEN, a propósito, y DISTINTO del fail-closed que usa la
revocación de tokens en `api/auth.py`: si Redis no está disponible, este
limitador deja pasar el tráfico (marcando `fail_open=True` para que
quien llame pueda loguearlo) en vez de rechazarlo. La revocación de
tokens es una decisión de SEGURIDAD (mejor rechazar de más que dejar
pasar un token robado/revocado). El rate limiting es una decisión de
DISPONIBILIDAD (mejor que un tenant se quede sin límite unos segundos a
que TODOS los tenants se queden sin servicio porque Redis tuvo un blip).
Son decisiones opuestas a propósito, no una inconsistencia.
"""
import time
from dataclasses import dataclass

import redis


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int
    fail_open: bool = False


class RateLimiter:
    def __init__(self, redis_client: "redis.Redis"):
        self._r = redis_client

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        """¿Se permite una petición más para `key` en esta ventana?

        `key` ya debe venir con su scope incluido (ej. "org:acme-colegio"
        o "auth_ip:203.0.113.5") para que tenants/IPs distintos no
        compartan contador por accidente."""
        now = time.time()
        window_start = int(now // window_seconds) * window_seconds
        redis_key = f"ratelimit:{key}:{window_start}"
        reset_seconds = max(0, window_start + window_seconds - int(now))

        try:
            count = self._r.incr(redis_key)
            if count == 1:
                # Solo el primero en la ventana pone el TTL — evita que
                # una carrera entre 2 requests casi simultáneas reinicie
                # el expire y la ventana nunca cierre.
                self._r.expire(redis_key, window_seconds)
        except Exception:
            return RateLimitResult(
                allowed=True, limit=limit, remaining=limit,
                reset_seconds=window_seconds, fail_open=True,
            )

        if count > limit:
            return RateLimitResult(allowed=False, limit=limit, remaining=0, reset_seconds=reset_seconds)
        return RateLimitResult(allowed=True, limit=limit, remaining=max(0, limit - count), reset_seconds=reset_seconds)
