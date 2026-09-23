"""
Cliente del LLM que usan todos los agentes (3 base + GradingAgent +
ContentGeneratorAgent + 10 agentes de materia).

TRANSPARENCIA: este entorno de desarrollo no tiene configuradas API keys
reales, así que este cliente, en orden de preferencia:
  1) Proveedor PRIMARIO: si existe ANTHROPIC_API_KEY, llama a la API real
     de Claude vía requests HTTP directos.
  2) Proveedor de RESPALDO (nuevo): si el primario no está configurado, o
     si está configurado pero falla (timeout, error HTTP, rate limit) y su
     circuit breaker no está abierto, se intenta un segundo proveedor.
     Configurable por env: OPENAI_API_KEY (compatible con la API de chat
     completions de OpenAI) tiene prioridad; si no está, se prueba
     ANTHROPIC_FALLBACK_API_KEY (una segunda cuenta/región de Anthropic —
     útil cuando el problema es specific-account rate limiting, no que
     Anthropic esté caído).
  3) Mock determinístico: si NO hay ningún proveedor real configurado, o
     si TODOS los proveedores reales configurados fallaron para esta
     llamada, se usa un mock determinístico — así el pipeline nunca se
     cae por falta de LLM, pero tampoco se finge silenciosamente que hubo
     una respuesta real cuando no la hubo (se loguea como error).

Esto es exactamente el punto de integración que se reemplaza cuando el
proyecto se conecta a producción; no hay que tocar nada más del pipeline
para agregar un proveedor real o cambiar cuál es el de respaldo.

**Qué está probado en este entorno** (`tests/test_llm_client.py`): la
lógica de selección de proveedor, el failover primario→respaldo→mock, y
el circuit breaker (abre tras N fallos consecutivos, deja de intentar el
proveedor caído durante el cooldown, y hace un intento de prueba
"half-open" pasado ese tiempo) — todo probado inyectando funciones falsas
en el punto exacto donde este módulo llamaría a la red real
(`_call_anthropic`/`_call_openai_compatible`), sin red de verdad, mismo
patrón que ya usaba este archivo para el modo mock. **No probado aquí**:
la llamada HTTP real a api.anthropic.com o api.openai.com con una API key
válida — igual que antes de este cambio.
"""
import json
import os
import time
import hashlib
import logging

logger = logging.getLogger("ai-agents-engine.llm_client")

USE_REAL_LLM = bool(os.getenv("ANTHROPIC_API_KEY"))


def _mock_response(system_prompt: str, user_text: str) -> str:
    """Genera una respuesta determinística y válida en formato JSON,
    basada en palabras clave simples, SOLO para poder probar el pipeline
    sin una API key real."""
    lower = user_text.lower()

    # Marcadores más específicos primero, mismo motivo que el comentario
    # original de abajo: evitar que un prompt más genérico capture por
    # error el texto de un agente nuevo.
    if "needs_teacher_review" in system_prompt:
        return _mock_grading_response(user_text)

    if "correct_index" in system_prompt:
        return _mock_quiz_response(user_text)

    if "final_answer" in system_prompt:
        return _mock_exercise_response(system_prompt, user_text)

    # IMPORTANTE: se revisa primero el marcador mas especifico ("component_type")
    # porque el prompt del compilador de UI tambien menciona la frase
    # "decision pedagogica" en su texto, lo que podia confundirse con el
    # prompt del agente pedagogico si se revisaba en el orden equivocado.
    if "component_type" in system_prompt:
        if "triangulo" in lower:
            return json.dumps({"component_type": "object3d", "payload": {"shape": "triangle", "color": "#00e0ff"}})
        return json.dumps({"component_type": "highlight", "payload": {"text": user_text[:40]}})

    if "extractor semántico" in system_prompt.lower():
        topic = "geometria" if "triangulo" in lower or "angulo" in lower else "general"
        return json.dumps({"text": user_text, "topic": topic, "confidence": 0.82})

    if '"action"' in system_prompt:
        if "triangulo" in lower or "figura" in lower:
            return json.dumps({"action": "render_3d_object", "reason": "Se menciona una figura geometrica", "priority": "high"})
        if "formula" in lower or "ecuacion" in lower or "=" in lower:
            return json.dumps({"action": "render_formula", "reason": "Se menciona una formula", "priority": "medium"})
        return json.dumps({"action": "no_action", "reason": "No amerita cambio visual", "priority": "low"})

    return json.dumps({"error": "prompt no reconocido por el mock"})


def _mock_grading_response(user_text: str) -> str:
    """Mock del grading_agent: espera un user_text con formato
    'Pregunta: ...\\nRespuesta del alumno: ...\\nPuntos clave esperados: p1, p2, ...'
    y calcula cuántos puntos clave aparecen literalmente en la respuesta —
    heurística simple pero determinística, suficiente para probar el
    contrato del schema sin una API key real."""
    lines = {}
    for line in user_text.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            lines[key.strip().lower()] = value.strip()

    answer = lines.get("respuesta del alumno", "").lower()
    key_points_raw = lines.get("puntos clave esperados", "")
    key_points = [p.strip() for p in key_points_raw.split(",") if p.strip()]

    # Bug real encontrado corriendo el test: un substring exacto
    # ("tres lados iguales" in answer) fallaba con respuestas válidas
    # como "sus tres lados ... son iguales", donde las palabras están
    # presentes pero no contiguas en ese orden. Se corrigió a exigir que
    # TODAS las palabras del punto clave aparezcan en la respuesta,
    # sin importar el orden — heurística más realista para lenguaje
    # natural, aunque siga siendo un mock y no un LLM real.
    def _all_words_present(point: str) -> bool:
        return all(word in answer for word in point.lower().split())

    matched = [p for p in key_points if _all_words_present(p)]
    score = (len(matched) / len(key_points)) if key_points else 0.0
    needs_review = len(answer) < 5 or score < 0.34

    feedback = (
        "Respuesta muy corta o ambigua, requiere revisión del profesor."
        if needs_review
        else f"Se identificaron {len(matched)} de {len(key_points)} puntos clave esperados."
    )

    return json.dumps({
        "score": round(score, 2),
        "matched_key_points": matched,
        "feedback": feedback,
        "needs_teacher_review": needs_review,
    })


def _mock_quiz_response(user_text: str) -> str:
    """Mock del content_generator_agent: genera una pregunta simple de
    verdadero/falso derivada del fragmento, determinística por palabras
    clave (mismo patrón que el resto de los mocks de este archivo)."""
    lower = user_text.lower()
    if "triangulo" in lower or "ángulo" in lower or "angulo" in lower:
        question = {
            "question": "¿El triángulo equilátero tiene sus tres ángulos internos iguales?",
            "options": ["Verdadero", "Falso"],
            "correct_index": 0,
        }
    elif "formula" in lower or "área" in lower or "area" in lower:
        question = {
            "question": f"Según lo explicado, ¿'{user_text.strip()[:60]}' describe una fórmula?",
            "options": ["Verdadero", "Falso"],
            "correct_index": 0,
        }
    else:
        question = {
            "question": f"¿El fragmento '{user_text.strip()[:60]}' contiene un concepto nuevo de la clase?",
            "options": ["Verdadero", "Falso"],
            "correct_index": 0,
        }
    return json.dumps({"questions": [question]})


def _mock_exercise_response(system_prompt: str, user_text: str) -> str:
    """Mock de los subject_agents/: genera un ejercicio ORIGINAL resuelto
    paso a paso, nunca copiado de ningún libro. Es una heurística por
    materia — no un banco de ejercicios de un libro real — pensada solo
    para probar de verdad que el esquema SolvedExercise y el pipeline
    funcionan sin necesitar una API key. La rama real (ANTHROPIC_API_KEY)
    es la que genera contenido pedagógicamente serio en producción.
    """
    import re

    match = re.search(r"profesor de (.+?) que redacta", system_prompt)
    subject = match.group(1).lower() if match else "general"

    lines = {}
    for line in user_text.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            lines[key.strip().lower()] = value.strip()
    topic = lines.get("tema", "").lower()
    difficulty = lines.get("dificultad", "basico") or "basico"
    if difficulty not in ("basico", "intermedio", "avanzado"):
        difficulty = "basico"

    if "matemática" in subject or "matematica" in subject:
        if "geometr" in subject or "área" in topic or "area" in topic or "triangulo" in topic:
            ex = {
                "statement": "Un terreno triangular tiene una base de 12 metros y una altura de 7 metros respecto a esa base. Calcula su área.",
                "steps": [
                    "El área de un triángulo se calcula como (base × altura) / 2.",
                    "Sustituyendo: área = (12 × 7) / 2 = 84 / 2.",
                ],
                "final_answer": "El área del terreno es 42 metros cuadrados.",
            }
        elif "trigonometr" in subject:
            ex = {
                "statement": "En un triángulo rectángulo, el cateto opuesto a un ángulo mide 6 cm y la hipotenusa mide 10 cm. Calcula el seno de ese ángulo.",
                "steps": [
                    "El seno de un ángulo se define como cateto opuesto / hipotenusa.",
                    "Sustituyendo: sen(θ) = 6 / 10 = 0.6.",
                ],
                "final_answer": "sen(θ) = 0.6",
            }
        elif "cálculo" in subject or "calculo" in subject or "derivada" in topic:
            ex = {
                "statement": "Calcula la derivada de la función f(x) = x² + 3x respecto a x.",
                "steps": [
                    "Se deriva término por término usando la regla de la potencia: d/dx[xⁿ] = n·xⁿ⁻¹.",
                    "La derivada de x² es 2x. La derivada de 3x es 3.",
                ],
                "final_answer": "f'(x) = 2x + 3",
            }
        elif "estadística" in subject or "estadistica" in subject:
            ex = {
                "statement": "Un estudiante obtuvo las siguientes notas en 4 exámenes: 14, 16, 12, 18. Calcula el promedio.",
                "steps": [
                    "El promedio (media aritmética) es la suma de los valores dividida entre la cantidad de valores.",
                    "Suma: 14 + 16 + 12 + 18 = 60. Cantidad de valores: 4.",
                ],
                "final_answer": "El promedio es 60 / 4 = 15.",
            }
        else:  # álgebra u otra área no listada explícitamente, fallback razonable
            ex = {
                "statement": "Resuelve la ecuación lineal: 3x + 7 = 22.",
                "steps": [
                    "Se resta 7 en ambos lados de la ecuación: 3x = 22 - 7 = 15.",
                    "Se divide ambos lados entre 3 para despejar x: x = 15 / 3.",
                ],
                "final_answer": "x = 5",
            }
    elif "física" in subject or "fisica" in subject:
        ex = {
            "statement": "Un ciclista recorre 60 km en 2 horas a velocidad constante. Calcula su velocidad media.",
            "steps": [
                "En movimiento rectilíneo uniforme, la velocidad media es distancia / tiempo.",
                "Sustituyendo: v = 60 km / 2 h.",
            ],
            "final_answer": "v = 30 km/h",
        }
    elif "química" in subject or "quimica" in subject:
        ex = {
            "statement": "Calcula la masa molar aproximada del agua (H₂O), sabiendo que H ≈ 1 g/mol y O ≈ 16 g/mol.",
            "steps": [
                "El agua tiene 2 átomos de hidrógeno y 1 de oxígeno.",
                "Masa molar = (2 × 1) + (1 × 16) = 2 + 16.",
            ],
            "final_answer": "La masa molar del agua es aproximadamente 18 g/mol.",
        }
    elif "biología" in subject or "biologia" in subject:
        ex = {
            "statement": "Explica, paso a paso, qué ocurre durante la fotosíntesis en una planta expuesta a luz solar.",
            "steps": [
                "La planta capta luz solar mediante la clorofila presente en los cloroplastos.",
                "Con esa energía, transforma agua (absorbida por la raíz) y dióxido de carbono (absorbido del aire) en glucosa y oxígeno.",
            ],
            "final_answer": "La planta produce glucosa (su alimento) y libera oxígeno como producto secundario.",
        }
    elif "anatomía" in subject or "anatomia" in subject:
        ex = {
            "statement": "Un alumno palpa su antebrazo y siente dos huesos largos y paralelos. Identifica cuáles son y su función principal.",
            "steps": [
                "El antebrazo humano está formado por dos huesos largos: el radio y el cúbito (o ulna).",
                "El radio permite el giro de la muñeca (pronación/supinación); el cúbito da estabilidad al codo.",
            ],
            "final_answer": "Los huesos son el radio y el cúbito.",
        }
    elif "inglés" in subject or "ingles" in subject:
        ex = {
            "statement": "Complete the sentence with the correct verb form: 'She ___ (to study) English every day.'",
            "steps": [
                "The sentence describes a routine/habit, which in English uses the Simple Present tense.",
                "For third person singular ('she'), the verb takes an -s ending: study -> studies.",
            ],
            "final_answer": "She studies English every day.",
        }
    else:
        ex = {
            "statement": f"Ejercicio de práctica sobre '{topic or 'el tema indicado'}' en {subject}.",
            "steps": [
                "Identifica los datos que da el enunciado.",
                "Aplica el concepto correspondiente al tema para llegar a la respuesta.",
            ],
            "final_answer": "Respuesta según el desarrollo anterior.",
        }

    ex["difficulty"] = difficulty
    return json.dumps(ex)


def _call_anthropic(system_prompt: str, user_text: str, api_key: str, model: str) -> str:
    """Llamada real a la API de mensajes de Anthropic. Función standalone
    (no un método) a propósito: es el punto exacto que los tests
    reemplazan con `monkeypatch.setattr` para probar el failover sin red
    real, y es el mismo patrón para cualquier proveedor nuevo que se
    agregue después."""
    import requests  # import local para no exigir la dependencia en modo mock

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 300,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_text}],
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def _call_openai_compatible(system_prompt: str, user_text: str, api_key: str, model: str, base_url: str) -> str:
    """Llamada a cualquier API compatible con /chat/completions de OpenAI
    (OpenAI real, o un proxy/gateway compatible). Proveedor de respaldo
    preferido sobre una segunda cuenta de Anthropic cuando está
    configurado, porque un incidente que afecte a la infraestructura de
    Anthropic completa (no solo una cuenta) no tumbaría a este también."""
    import requests

    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 300,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


class CircuitBreaker:
    """Circuit breaker simple de 3 estados (cerrado/abierto/half-open),
    uno por proveedor. Evita machacar un proveedor caído con timeouts de
    15s en cada fragmento de transcripción mientras la clase sigue en
    vivo — sin esto, un LLM primario caído podía multiplicar la latencia
    de CADA agente por el timeout completo antes de intentar el respaldo.

    Estados:
      - Cerrado (failures < threshold): llama al proveedor normalmente.
      - Abierto (failures >= threshold, dentro de reset_timeout desde que
        abrió): NO llama al proveedor, salta directo al siguiente.
      - Half-open (abierto pero ya pasó reset_timeout): permite UN
        intento de prueba; si funciona, cierra: si falla, vuelve a abrir
        y reinicia el cooldown.
    """

    def __init__(self, failure_threshold: int = 3, reset_timeout_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.consecutive_failures = 0
        self.opened_at: float | None = None

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if (time.monotonic() - self.opened_at) >= self.reset_timeout_seconds:
            return False  # half-open: se permite un intento de prueba
        return True

    def record_success(self):
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.opened_at = time.monotonic()


# Un breaker por proveedor, persistente entre llamadas dentro del mismo
# proceso (igual que el registry de agentes en orchestrator/registry.py).
_circuit_breakers: dict[str, CircuitBreaker] = {}


def _get_breaker(provider_name: str) -> CircuitBreaker:
    if provider_name not in _circuit_breakers:
        _circuit_breakers[provider_name] = CircuitBreaker(
            failure_threshold=int(os.getenv("LLM_CIRCUIT_FAILURE_THRESHOLD", "3")),
            reset_timeout_seconds=float(os.getenv("LLM_CIRCUIT_RESET_SECONDS", "30")),
        )
    return _circuit_breakers[provider_name]


def reset_circuit_breakers():
    """Limpia el estado de todos los breakers. Solo para tests — en
    producción el estado debe persistir mientras viva el proceso."""
    _circuit_breakers.clear()


def _build_providers() -> list[dict]:
    """Se reconstruye en CADA llamada a partir del entorno (mismo patrón
    que `_rate_limit_config()` en core-erp-backend/main.py): permite que
    los tests cambien variables de entorno con `monkeypatch.setenv` sin
    tener que recargar el módulo, y que un operador rote una API key sin
    reiniciar el proceso... salvo que el proceso cachea el import; en
    producción real esto solo importa si además se recarga el módulo,
    pero mantiene el comportamiento consistente con el resto del proyecto."""
    providers = []

    if os.getenv("ANTHROPIC_API_KEY"):
        api_key = os.environ["ANTHROPIC_API_KEY"]
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        providers.append({
            "name": "anthropic_primary",
            "call": lambda sp, ut, _k=api_key, _m=model: _call_anthropic(sp, ut, _k, _m),
        })

    if os.getenv("OPENAI_API_KEY"):
        api_key = os.environ["OPENAI_API_KEY"]
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        providers.append({
            "name": "openai_fallback",
            "call": lambda sp, ut, _k=api_key, _m=model, _b=base_url: _call_openai_compatible(sp, ut, _k, _m, _b),
        })
    elif os.getenv("ANTHROPIC_FALLBACK_API_KEY"):
        api_key = os.environ["ANTHROPIC_FALLBACK_API_KEY"]
        model = os.getenv("ANTHROPIC_FALLBACK_MODEL", "claude-sonnet-4-6")
        providers.append({
            "name": "anthropic_fallback",
            "call": lambda sp, ut, _k=api_key, _m=model: _call_anthropic(sp, ut, _k, _m),
        })

    return providers


def call_llm(system_prompt: str, user_text: str) -> str:
    providers = _build_providers()
    attempted_any_real_provider = False
    last_error: Exception | None = None

    for provider in providers:
        breaker = _get_breaker(provider["name"])
        if breaker.is_open():
            logger.warning(
                "llm_provider_skipped_circuit_open provider=%s cooldown_seconds=%.0f",
                provider["name"], breaker.reset_timeout_seconds,
            )
            continue

        attempted_any_real_provider = True
        try:
            result = provider["call"](system_prompt, user_text)
            breaker.record_success()
            return result
        except Exception as exc:  # noqa: BLE001 — cualquier fallo del proveedor debe activar el failover
            breaker.record_failure()
            last_error = exc
            logger.warning(
                "llm_provider_failed provider=%s consecutive_failures=%d error=%s",
                provider["name"], breaker.consecutive_failures, exc,
            )
            continue

    # Todos los proveedores reales configurados fallaron (o sus breakers
    # están abiertos), o no hay ninguno configurado: último recurso, el
    # mock determinístico. Si SÍ había proveedores reales y todos
    # fallaron, se loguea como error (no como el camino normal) para que
    # esto sea visible en monitoreo real, a diferencia del caso "no hay
    # ninguna key configurada" que es esperado en este sandbox.
    if attempted_any_real_provider and last_error is not None:
        logger.error(
            "llm_all_providers_failed falling_back_to_mock last_error=%s", last_error,
        )
    return _mock_response(system_prompt, user_text)
