# Prompt de arranque — Colegio Virtual: Aula Virtual en Vivo

> **Rige el Apéndice A de CLAUDE.md**: ningún archivo se fusiona por compacidad. Gate G47 antes de cada commit.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: vive como `colegio_virtual_virtual_classroom` en `module_backlog.yaml`, gate G39 heredado de la Pizarra.

Mismo repositorio `erp-enterprise/` **más** el repositorio `smart-whiteboard/` ya con `whiteboard_sketch_engine` completo — esta sesión conecta dos repos, no es autocontenida.

---

## PROMPT

Lee `CLAUDE.md` (ERP) Y `CLAUDE.md` de la Pizarra (Adenda V15 §75, `whiteboard_connector.py`, ya con código de referencia). Lee también el análisis de fallas de la Pizarra (documento Pizarra, sección de resiliencia/`DegradedModeManager`) — el punto 2 de ese análisis dice explícitamente que un aula virtual EN VIVO no puede degradar igual que la Pizarra física (§74 del ERP, V15): si un estudiante pierde conexión, se está perdiendo la clase, no puede "seguir trabajando local".

**Objetivo**: `session_manager.py`, `attendance_tracker.py` (código de referencia completo en V15 §75), `whiteboard_connector.py` (código de referencia completo en V15 §75), `live_video_bridge.py`, `breakout_rooms.py`.

**Decisión ya resuelta**: LiveKit self-hosted (V17 §88) para `live_video_bridge.py` — no evalúes otros proveedores en esta sesión, esa decisión ya está tomada y justificada.

**Alcance**:
1. `IMPLEMENT`: `live_video_bridge.py` sobre LiveKit — sesión de video con roles (profesor puede silenciar/expulsar, estudiante no).
2. `IMPLEMENT`: `whiteboard_connector.py` — código ya dado, impléméntalo importando `whiteboard_platform.collaboration.session_manager` como dependencia real (verifica que el paquete compartido entre repos existe; si no, créalo como parte de esta sesión, es infraestructura, no lógica de negocio nueva).
3. `IMPLEMENT`: `attendance_tracker.py` — código ya dado (`determine_attendance()` con las 4 categorías PRESENT/PRESENT_PASSIVE/PARTIAL/ABSENT).
4. `IMPLEMENT`: modo de degradación específico de esta sesión (distinto al de la Pizarra física) — reconexión rápida con buffer corto + aviso claro de "te perdiste los últimos N minutos, aquí está la grabación" en vez de intentar seguir localmente sin la clase en vivo.
5. `QA`: prueba del caso límite de asistencia — estudiante conectado 85% del tiempo pero sin ninguna interacción → debe quedar `PRESENT_PASSIVE`, nunca `PRESENT` silenciosamente.

**Qué NO hacer**: no implementes `proctoring/` (evaluaciones supervisadas son otra sesión) ni reescribas el CRDT de la Pizarra — se importa, no se copia.

Al terminar: resumen de siempre + confirmación de que probaste una desconexión a mitad de sesión y el comportamiento fue "reconexión + grabación disponible", no "silencio" ni "crash".
