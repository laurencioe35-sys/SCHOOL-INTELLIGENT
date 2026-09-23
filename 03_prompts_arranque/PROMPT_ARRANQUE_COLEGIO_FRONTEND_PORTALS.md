# Prompt de arranque — Colegio Virtual: Portales de Frontend (estudiante/profesor/acudiente)

> **Rige el Apéndice A de CLAUDE.md**: ningún componente se fusiona por compacidad. Gate G47 antes de cada commit.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: vive como `colegio_virtual_frontend_portals` en `module_backlog.yaml`, gate G62.

Mismo repositorio. Requiere `colegio_virtual_gradebook` y `colegio_virtual_virtual_classroom` — los portales consumen esos endpoints, no tiene sentido construirlos antes.

---

## PROMPT

Lee `CLAUDE.md`, Adenda V22 completa (árbol de los 3 portales + `GradesView.tsx` como código de referencia). El punto más importante de esta sesión no es visual — es el análisis de la sección 106: **ningún componente de estos 3 portales puede refiltrar en el cliente datos que el backend ya debería filtrar por RLS**. Antes de escribir cada componente que consuma datos de estudiante/calificación/asistencia, verifica que el endpoint que vas a llamar ya resuelve "el usuario actual" del lado del servidor (`/me/...`, nunca un ID parametrizable desde el cliente para vistas de "mis propios datos").

**Objetivo**: implementar los 3 portales completos siguiendo el árbol de V22 §105.

**Alcance**:
1. `IMPLEMENT`: `student-portal/` — `GradesView.tsx` ya dado como referencia; `StudentDashboard.tsx`, `LiveClassJoin.tsx`, `TranscriptDownload.tsx` siguiendo el mismo patrón (`/students/me/...`).
2. `IMPLEMENT`: `teacher-portal/` — `GradebookEditor.tsx` debe enviar la calificación cruda al backend y mostrar el resultado de `grade_calculation_engine.py` (V16) que el backend calcula — **nunca calcules el promedio ponderado en el cliente**, ni siquiera para mostrar una vista previa; si hace falta una vista previa, pide un endpoint que corra la misma función pura del backend, no reimplementes la fórmula en TypeScript.
3. `IMPLEMENT`: `parent-portal/` — reutiliza el rol `guardian` ya definido en la Pizarra (§9 del documento Pizarra) — no crees un rol nuevo con el mismo propósito.
4. `SECURITY`: gate **G62** — para cada componente que consuma datos "propios" del usuario, verifica inspeccionando la respuesta real del endpoint (no solo el código del componente) que nunca llega más de un estudiante/acudiente en el payload cuando la vista es individual.
5. `QA`: prueba de accesibilidad básica en los 3 dashboards (reutiliza `axe-core`, ya definido como dependencia del ERP) — un portal educativo usado por familias diversas no puede asumir que todos navegan igual.

**Qué NO hacer**: no dupliques lógica de negocio (cálculo de notas, validación de elegibilidad, reglas de asistencia) en el frontend — todo eso ya vive en el backend con sus pruebas; el frontend solo presenta y envía acciones.

Al terminar: resumen de siempre + confirmación explícita, componente por componente, de que ninguno calcula o refiltra datos sensibles del lado del cliente — es la evidencia central de esta sesión, no un detalle secundario.
