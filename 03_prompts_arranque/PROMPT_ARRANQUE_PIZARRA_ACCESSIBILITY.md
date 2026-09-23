# Prompt de arranque — Pizarra: Accesibilidad (Captions en Vivo)

> **Rige el Apéndice A**. Gate G47.

## Antes de pegar en Claude Code
> Vive como `accessibility` en el backlog, gate G37. Requiere `sketch_engine`.

## PROMPT
Lee `CLAUDE.md`, sección 20 (`LiveCaptionsOverlay.tsx` — código de referencia completo) y la sección 15 del ERP (`voice_assistant/stt/`).

**Objetivo**: subtítulos en vivo reutilizando el motor STT YA construido en el ERP — esta sesión NO crea un motor de reconocimiento de voz propio.

**Alcance**: `LiveCaptionsOverlay.tsx` tal cual; descripción textual equivalente (`aria-describedby`) para cada figura/expresión reconocida, para lector de pantalla.

**Qué NO hacer**: no implementes tu propio STT — importa el del ERP como dependencia de plataforma.

Al terminar: resumen de siempre + prueba con lector de pantalla real (o su emulador) confirmando que una figura convertida se anuncia correctamente.
