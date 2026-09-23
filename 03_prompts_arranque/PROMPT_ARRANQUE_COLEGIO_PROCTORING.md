# Prompt de arranque — Colegio Virtual: Evaluación Supervisada (Proctoring)

> **Rige el Apéndice A de CLAUDE.md**: ningún archivo se fusiona por compacidad. Gate G47 antes de cada commit.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: vive como `colegio_virtual_proctoring` en `module_backlog.yaml`, gate G32 heredado de la Pizarra (consentimiento de menor).

Mismo repositorio. Requiere `colegio_virtual_gradebook` (una evaluación supervisada termina en una calificación) y el protocolo de consentimiento de la Pizarra (`dataset_collection.py`, sección de consentimiento) como referencia de patrón — no como dependencia directa de código, sino de criterio.

---

## PROMPT

Lee `CLAUDE.md`, Adenda V15 (§73, árbol de `proctoring/`) y el agente **Academic-Integrity** (V16 §79) — su alcance es explícito: señales de irregularidad, **NUNCA biometría facial por defecto**, nunca decide sanciones. Esta es probablemente la sesión de mayor riesgo de privacidad de todo el vertical educativo — trátala con el mismo cuidado que la sección de dataset de la Pizarra.

**Objetivo**: `exam_session_service.py`, `integrity_flagging.py`, `proctoring_disclosure.py`.

**Alcance**:
1. `IMPLEMENT`: `proctoring_disclosure.py` — **va primero**, igual que `opt_in_registry.py` fue primero en la sesión de WhatsApp. Ninguna señal de supervisión se activa sin consentimiento verificado y registrado, con el mismo nivel de explicitud que el protocolo de la Pizarra (qué se supervisa, por cuánto tiempo, quién lo ve).
2. `IMPLEMENT`: `integrity_flagging.py` — señales basadas en patrones de interacción (cambios de pestaña, tiempo de respuesta anómalo, copiar/pegar de texto largo) — **explícitamente NO** captura de cámara/rostro por defecto. Si el colegio quiere activar cámara, es una configuración aparte con su propio consentimiento reforzado, no el comportamiento por defecto de este módulo.
3. `IMPLEMENT`: cada señal generada queda auditada con el detalle exacto (qué patrón se detectó, con qué confianza) — nunca "posible fraude" sin evidencia trazable.
4. `SECURITY`: gate **G32** (ya definido, heredado de la Pizarra) — prueba de que ninguna función de supervisión se activa sin consentimiento verificado primero.
5. `QA`: prueba de que una señal de alta confianza notifica a coordinación académica con evidencia adjunta, pero **no aplica ninguna sanción automáticamente** — el agente Academic-Integrity tiene eso explícitamente fuera de alcance.

**Qué NO hacer**: no implementes reconocimiento facial ni ningún tipo de biometría en esta sesión, aunque parezca "mejorar la precisión" — es una decisión de producto explícitamente fuera de alcance por defecto, documentada así a propósito.

Al terminar: resumen de siempre + confirmación explícita de qué señales SÍ se implementaron (para que quede claro que ninguna involucra biometría) y qué consentimiento exacto viste antes de activar cada una.
