# Prompt de arranque — Colegio Virtual: Cumplimiento Normativo (regulatory_compliance/)

> **Rige el Apéndice A de CLAUDE.md**: ningún archivo se fusiona por compacidad. Gate G47 (con las 4 heurísticas de V12-V23) antes de cada commit.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: vive como `colegio_virtual_regulatory_compliance` en `module_backlog.yaml`.

Mismo repositorio. Requiere `colegio_virtual_admissions`, `colegio_virtual_gradebook` y `colegio_virtual_credentials` — este módulo solo agrega datos que esos tres ya producen, no genera nada propio.

---

## PROMPT

Lee `CLAUDE.md`, Adenda V24 (`ministry_reporting.py`, código+prueba de referencia completos). Esta sesión es distinta a las anteriores en un punto importante: **no vas a decidir el formato final del reporte** — esa es una decisión de negocio explícitamente pendiente (normativa exacta del país), documentada así a propósito. Si te encuentras "completando" un `MinistryReportFormatter` concreto con campos que suenan plausibles para el MEN de Colombia u otro país sin una fuente oficial verificada que yo te haya dado, detente — eso sería inventar normativa, exactamente lo que el contrato prohíbe desde V15 §78.

**Objetivo**: implementar `aggregate_regulatory_report_data()` y la interfaz `MinistryReportFormatter` tal cual (V24), completando las funciones de agregación (`_count_enrolled_students`, `_count_graduated_students`, `_average_attendance_rate`, `_grade_distribution`) contra los módulos ya construidos — nunca un cálculo paralelo.

**Alcance**:
1. `IMPLEMENT`: las 4 funciones de agregación, cada una consultando el módulo dueño del dato (`admissions` para matrícula, `credentials`/`certificate_generator.py` para graduados, `virtual_classroom`/`attendance_tracker.py` para asistencia, `gradebook` para distribución de notas) — nunca dupliques la lógica de conteo, solo agrégala.
2. `IMPLEMENT`: un `MinistryReportFormatter` de **prueba/desarrollo** (ej. formato JSON plano) para poder probar el pipeline completo — explícitamente marcado como no apto para envío real a ninguna autoridad, solo para verificar que la agregación funciona.
3. `QA`: prueba de que `generate_report_for_review()` nunca envía nada — solo retorna bytes para revisión humana. Si en algún punto agregas una llamada a un servicio externo de envío dentro de este flujo, es un error de alcance, corrígelo.

**Qué NO hacer**: no implementes `regulatory_submission.py` (el envío real) — es explícitamente una pieza separada y futura, mencionada pero fuera de alcance en V24. No inventes campos de normativa educativa real.

Al terminar: resumen de siempre + confirmación explícita de que el formatter implementado está marcado como "solo desarrollo", no como listo para uso oficial.
