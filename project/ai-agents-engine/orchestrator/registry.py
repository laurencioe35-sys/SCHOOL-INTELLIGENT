"""
Registro de agentes ("receptor de multiagentes").

Esto es lo que hace que el ERP pueda crecer en agentes sin que el loop
central (loop_engine.py) tenga que conocer a cada uno por nombre: un
agente nuevo se escribe una vez implementando `BaseAgent`, se registra
con `@register_agent(...)`, y desde ese momento el loop lo invoca solo
cuando el tipo de evento le interesa (`interests`).

Aislamiento de fallos: si un agente lanza una excepción, el loop lo
registra como error y sigue con los demás agentes y el siguiente evento
— un agente roto no debe tumbar la clase en vivo completa. Esto se prueba
explícitamente en tests/test_orchestrator.py.

--- NUEVO: Circuit breaker por agente -------------------------------
En un salón con 30+ alumnos y varios agentes registrados, un agente que
empieza a fallar sistemáticamente (proveedor LLM caído, un bug real, un
timeout de red) no debería seguir intentándose en CADA evento: eso
desperdicia latencia y presupuesto de LLM en una llamada que ya sabemos
que va a fallar. `CircuitBreaker` trae ese agente offline temporalmente
después de N fallos consecutivos, y lo vuelve a intentar solo de vez en
cuando (half-open) para detectar recuperación automática — sin que
nadie tenga que reiniciar el proceso a mano. Esto no existía en el
proyecto y se prueba en tests/test_resilience.py con un reloj inyectado
(sin sleeps reales, determinista).
"""
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, ClassVar


@dataclass
class AgentResult:
    agent_name: str
    ok: bool
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    circuit_skipped: bool = False


class CircuitState(str, Enum):
    CLOSED = "closed"      # funcionando normal, se ejecuta el agente
    OPEN = "open"           # demasiados fallos seguidos, se salta el agente
    HALF_OPEN = "half_open"  # cooldown vencido, se permite UN intento de prueba


@dataclass
class CircuitBreaker:
    """Circuit breaker simple de 3 estados por agente.

    - failure_threshold: fallos consecutivos antes de abrir el circuito.
    - cooldown_seconds: cuánto tiempo se salta el agente antes de probar
      de nuevo en half-open.
    - clock: inyectable para pruebas deterministas (por defecto time.monotonic).
    """

    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    clock: Callable[[], float] = field(default=time.monotonic)

    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    consecutive_failures: int = field(default=0, init=False)
    opened_at: float | None = field(default=None, init=False)
    total_trips: int = field(default=0, init=False)

    def allow_request(self) -> bool:
        """¿Se debe intentar ejecutar el agente en este ciclo?"""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            assert self.opened_at is not None
            if self.clock() - self.opened_at >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN: se permite el intento de prueba en curso; si otro
        # evento llega mientras ese intento no ha resuelto, se sigue
        # tratando como HALF_OPEN (single-flight aproximado, suficiente
        # para un loop secuencial como el nuestro que no es concurrente
        # dentro de una misma sesión de agente).
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.state == CircuitState.HALF_OPEN or self.consecutive_failures >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                self.total_trips += 1
            self.state = CircuitState.OPEN
            self.opened_at = self.clock()


class RedisCircuitBreaker:
    """Circuit breaker con estado en Redis, compartido entre TODAS las
    réplicas del ai-agents-engine (varios workers/procesos leyendo la
    misma cola). Sin esto, cada réplica traía su propio `CircuitBreaker`
    en memoria: un agente podía estar "abierto" en el worker A y "cerrado"
    en el worker B al mismo tiempo, lo que rompe el propósito de tener un
    breaker (coordinar una sola decisión: ¿este agente está sano o no?).

    IMPORTANTE — por qué el reloj por defecto es `time.time()` y no
    `time.monotonic()` como en `CircuitBreaker`: `time.monotonic()` solo
    es comparable DENTRO de un mismo proceso (dos procesos no comparten
    el mismo "cero"). Como este estado se comparte entre procesos vía
    Redis, comparar un `opened_at` guardado por el proceso A contra
    `clock()` del proceso B con monotonic() daría resultados sin sentido.
    `time.time()` (época UNIX) sí es comparable entre procesos siempre
    que los relojes de las máquinas estén sincronizados (NTP), que es la
    situación normal en cualquier clúster real.

    Se ejercita de verdad en tests/test_resilience_redis.py contra un
    Redis real (no es el patrón 'documentado pero no probado' del resto
    del proyecto — si Redis no está disponible, esos tests se saltan
    explícitamente en vez de fingir que corrieron)."""

    def __init__(
        self,
        agent_name: str,
        redis_url: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.time,
        namespace: str = "agents:circuit",
    ):
        import redis  # import local: mismo patrón de fallback honesto que blackboard.py

        self._r = redis.from_url(redis_url, decode_responses=True)
        self._key = f"{namespace}:{agent_name}"
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock

    def _load(self) -> dict:
        raw = self._r.hgetall(self._key)
        return {
            "state": CircuitState(raw.get("state", CircuitState.CLOSED.value)),
            "consecutive_failures": int(raw.get("consecutive_failures", 0)),
            "opened_at": float(raw["opened_at"]) if raw.get("opened_at") else None,
            "total_trips": int(raw.get("total_trips", 0)),
        }

    def _save(self, state: CircuitState, consecutive_failures: int, opened_at: float | None, total_trips: int) -> None:
        self._r.hset(self._key, mapping={
            "state": state.value,
            "consecutive_failures": consecutive_failures,
            "opened_at": "" if opened_at is None else opened_at,
            "total_trips": total_trips,
        })

    @property
    def state(self) -> CircuitState:
        return self._load()["state"]

    @property
    def consecutive_failures(self) -> int:
        return self._load()["consecutive_failures"]

    @property
    def opened_at(self) -> float | None:
        return self._load()["opened_at"]

    @property
    def total_trips(self) -> int:
        return self._load()["total_trips"]

    def allow_request(self) -> bool:
        s = self._load()
        if s["state"] == CircuitState.CLOSED:
            return True
        if s["state"] == CircuitState.OPEN:
            if self.clock() - s["opened_at"] >= self.cooldown_seconds:
                self._save(CircuitState.HALF_OPEN, s["consecutive_failures"], s["opened_at"], s["total_trips"])
                return True
            return False
        return True  # HALF_OPEN: se permite el intento de prueba en curso

    def record_success(self) -> None:
        s = self._load()
        self._save(CircuitState.CLOSED, 0, None, s["total_trips"])

    def record_failure(self) -> None:
        s = self._load()
        consecutive = s["consecutive_failures"] + 1
        total_trips = s["total_trips"]
        if s["state"] == CircuitState.HALF_OPEN or consecutive >= self.failure_threshold:
            if s["state"] != CircuitState.OPEN:
                total_trips += 1
            self._save(CircuitState.OPEN, consecutive, self.clock(), total_trips)
        else:
            self._save(s["state"], consecutive, s["opened_at"], total_trips)


def build_circuit_breaker(
    agent_name: str,
    redis_url: str | None = None,
    failure_threshold: int = 3,
    cooldown_seconds: float = 30.0,
    clock: Callable[[], float] | None = None,
):
    """Factory: Redis si ERP_REDIS_URL está configurado (estado
    compartido entre réplicas), memoria de proceso si no (igual patrón
    de fallback honesto que build_blackboard()/build_event_queue())."""
    redis_url = redis_url if redis_url is not None else os.getenv("ERP_REDIS_URL")
    if redis_url:
        try:
            return RedisCircuitBreaker(
                agent_name, redis_url,
                failure_threshold=failure_threshold, cooldown_seconds=cooldown_seconds,
                clock=clock or time.time,
            )
        except ImportError:
            pass  # sin el paquete redis instalado, cae a memoria
    return CircuitBreaker(failure_threshold=failure_threshold, cooldown_seconds=cooldown_seconds, clock=clock or time.monotonic)


class BaseAgent(ABC):
    """Contrato mínimo que debe cumplir cualquier agente para poder
    conectarse al loop. `interests` declara a qué tipos de evento
    reacciona (ej. 'transcript_chunk', 'student_submission')."""

    name: ClassVar[str]
    interests: ClassVar[tuple[str, ...]] = ("transcript_chunk",)

    @abstractmethod
    def handle(self, event: dict[str, Any], blackboard) -> Any:
        """Procesa el evento. Puede leer/escribir en el blackboard para
        coordinarse con otros agentes (ej. leer el 'topic' que ya dejó
        el context_agent en vez de volver a detectarlo)."""
        raise NotImplementedError


class AgentRegistry:
    def __init__(
        self,
        circuit_breaker_factory: Callable[[str], Any] | None = None,
    ):
        self._agents: dict[str, BaseAgent] = {}
        # Un circuit breaker independiente por agente: que "context_agent"
        # esté fallando no debe afectar el breaker de "analytics_agent".
        # La fábrica recibe el NOMBRE del agente (no solo un tipo vacío)
        # porque el breaker compartido en Redis necesita namespacear su
        # clave por agente (ver build_circuit_breaker / RedisCircuitBreaker).
        self._breakers: dict[str, Any] = {}
        self._circuit_breaker_factory = circuit_breaker_factory or build_circuit_breaker

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent
        self._breakers.setdefault(agent.name, self._circuit_breaker_factory(agent.name))

    def unregister(self, name: str) -> None:
        self._agents.pop(name, None)
        self._breakers.pop(name, None)

    def agents_for(self, event_type: str) -> list[BaseAgent]:
        return [a for a in self._agents.values() if event_type in a.interests]

    def all_agents(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def breaker_for(self, agent_name: str) -> Any:
        return self._breakers.get(agent_name)

    def open_circuits(self) -> list[str]:
        """Nombres de agentes actualmente offline por circuit breaker —
        lo que un dashboard de operaciones necesitaría mostrar en rojo."""
        return [name for name, cb in self._breakers.items() if cb.state == CircuitState.OPEN]

    def run_all(self, event: dict[str, Any], blackboard) -> list[AgentResult]:
        """Ejecuta cada agente interesado, aislando fallos individuales y
        respetando su circuit breaker: un agente con el circuito abierto
        se salta sin gastar tiempo ni presupuesto de LLM en un intento
        que ya sabemos que probablemente fallará."""
        results = []
        for agent in self.agents_for(event.get("type", "transcript_chunk")):
            breaker = self._breakers.setdefault(agent.name, self._circuit_breaker_factory(agent.name))

            if not breaker.allow_request():
                results.append(AgentResult(
                    agent_name=agent.name, ok=False,
                    error=f"circuit_open (fallos consecutivos: {breaker.consecutive_failures})",
                    circuit_skipped=True,
                ))
                continue

            start = time.monotonic()
            try:
                data = agent.handle(event, blackboard)
                duration_ms = (time.monotonic() - start) * 1000
                breaker.record_success()
                results.append(AgentResult(agent_name=agent.name, ok=True, data=data, duration_ms=duration_ms))
            except Exception as exc:  # aislamiento: un agente roto no tumba el loop
                duration_ms = (time.monotonic() - start) * 1000
                breaker.record_failure()
                results.append(AgentResult(agent_name=agent.name, ok=False, error=str(exc), duration_ms=duration_ms))
        return results
