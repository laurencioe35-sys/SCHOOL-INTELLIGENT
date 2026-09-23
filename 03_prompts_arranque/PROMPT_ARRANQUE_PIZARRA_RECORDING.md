# Prompt de arranque — Pizarra: Grabación y Repaso de Clase

> **Rige el Apéndice A**. Gate G47.

## Antes de pegar en Claude Code
> Vive como `recording_replay` en el backlog. Requiere `collaboration` completo.

## PROMPT
Lee `CLAUDE.md`, sección 19 (`stroke_event_log.py`, `replay_service.py` — código de referencia completo, mismo patrón append-only que `audit_log` del ERP).

**Objetivo**: grabación por EVENTOS (trazo, conversión de forma, transcripción de audio), nunca por video/píxel — un mismo reloj `t_offset_ms` para trazos y audio, sin desincronía.

**Alcance**: implementa `lesson_events` (tabla inmutable, mismo trigger de bloqueo de UPDATE/DELETE que `audit_log`), `ReplayTimelineScrubber.tsx` (reutiliza `VideoTimelineCarousel` del ERP, no crees un componente nuevo).

**Qué NO hacer**: no grabes video de pantalla — el repaso se reconstruye desde eventos.

Al terminar: resumen de siempre + demo de reproducir una clase de prueba con trazos+audio sincronizados desde los eventos guardados.
