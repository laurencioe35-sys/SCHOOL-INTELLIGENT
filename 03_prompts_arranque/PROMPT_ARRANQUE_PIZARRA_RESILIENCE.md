# Prompt de arranque — Pizarra: Capa de Resiliencia (Degradación Controlada)

> **Rige el Apéndice A**. Gate G47.

## Antes de pegar en Claude Code
> Vive como `resilience_layer` en el backlog, gates G38/G40. Requiere `sketch_engine` + `collaboration`.

## PROMPT
Lee `CLAUDE.md`, secciones 26-30 (matriz de modos de falla, `DegradedModeManager.ts`, `cost_circuit_breaker.py` — código de referencia completo).

**Objetivo**: la regla de oro del documento — `canWriteFreehand()` SIEMPRE retorna `true`, sin importar el modo (`ONLINE_FULL`/`DEGRADED_NO_AI`/`DEGRADED_LOCAL_ONLY`).

**Alcance**: implementa la máquina de estados completa + el circuit breaker de costo de IA con degradación progresiva (throttle → manual-only → disabled, nunca corte abrupto de escritura/voz local).

**Qué NO hacer**: no hagas que ninguna función de escritura a mano dependa de que la red o la IA estén disponibles — es la prueba central del gate G38.

Al terminar: resumen de siempre + prueba explícita: cortar la red a mitad de escritura → cero trazos perdidos al reconectar.
