# Prompt de arranque — Colegio Virtual: Calificaciones (Gradebook)

> **Rige el Apéndice A de CLAUDE.md**: ningún archivo se fusiona por compacidad. Gate G47 antes de cada commit.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: vive como `colegio_virtual_gradebook` en `module_backlog.yaml`.

Mismo repositorio. Requiere `colegio_virtual_curriculum` (necesita cursos reales para calificar) y `audit_rls` (toda calificación se audita desde el commit uno).

---

## PROMPT

Lee `CLAUDE.md`, Adenda V16 (`grade_calculation_engine.py`, código+pruebas completas) y V17-V18 (`report_card_generator.py`, `report_card_renderer.py`, `report_card_signature.py`, todos con código de referencia completo). Esta sesión no diseña lógica nueva — **ensambla y prueba de punta a punta** lo que el contrato ya especificó en detalle, porque es la sesión donde más piezas ya resueltas convergen.

**Objetivo**: `assignment_service.py` (el único archivo sin código de referencia previo) + integración real de los 4 archivos ya dados.

**Alcance**:
1. `IMPLEMENT`: `assignment_service.py` — CRUD de tareas/evaluaciones por curso, produciendo `GradeEntry` (el tipo ya definido en `grade_calculation_engine.py`, V16) — no redefinas un tipo paralelo.
2. `IMPLEMENT`: conecta el flujo completo — crear tarea → calificar → `calculate_weighted_average()` → `issue_report_card()` → `render_report_card_pdf()` → `sign_report_card()`. Si esta cadena no funciona de punta a punta con datos reales de prueba, la sesión no está completa aunque cada archivo individual pase sus pruebas unitarias por separado (mismo criterio que exigimos en la sesión de Pagos, V-Pagos §punto de integración).
3. `SECURITY`: gate **G52** (pesos que no suman 100% se rechazan), **G55** (ningún boletín firmado por `system` o rol no autorizado) — ambos ya definidos, verifícalos con prueba real, no de palabra.
4. `SECURITY`: aplica el agente **Gradebook-Integrity** (V16 §79) — un profesor no puede calificar y luego aprobar su propia apelación de nota sobre la misma calificación; reutiliza el mismo patrón de segregación de funciones de `permission_check.py` (Auditoría/RLS), no crees uno paralelo.

**Qué NO hacer**: no implementes `proctoring/` (calificación de exámenes supervisados es una sesión aparte) ni `virtual_classroom/` — esta sesión es solo sobre calificación y boletines, ya con todo su código base dado.

Al terminar: resumen de siempre + una demostración concreta de la cadena completa tarea→calificación→boletín→firma, con los IDs reales generados en cada paso — no una descripción, evidencia.
