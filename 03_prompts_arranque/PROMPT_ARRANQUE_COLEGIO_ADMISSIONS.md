# Prompt de arranque — Colegio Virtual: Admisiones (primer módulo del vertical educativo)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 antes de cada commit — gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP (id: `colegio_virtual_admissions`) y el orquestador lo consume automáticamente si le pides que ejecute el loop autónomo contra el backlog. Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal.

Mismo repositorio `erp-enterprise/`. Requiere que Auditoría/RLS ya exista (`audit_rls` en el backlog) — las decisiones de admisión son sensibles y deben auditarse desde el primer commit, no agregarse después.

---

## PROMPT

Lee `CLAUDE.md`, específicamente la Adenda V15 (vertical `colegio_virtual/`) y V16 (`eligibility_check.py`, ya con código de referencia completo — impléméntalo tal cual, no lo rediseñes). Este es el primer módulo del vertical educativo — todo lo demás (`curriculum`, `gradebook`, `virtual_classroom`, `proctoring`) depende de que admisiones exista primero, porque un estudiante debe estar matriculado antes de poder cursar, calificarse o entrar a una clase en vivo.

**Objetivo de esta sesión**: implementar `admissions/` completo — solicitud, verificación de elegibilidad, matrícula formal, lista de espera.

**Lo que el contrato YA resolvió — impléméntalo tal cual**:
- `eligibility_check.py` — `check_age_eligibility()` con margen de tolerancia y escalamiento a revisión humana en casos límite (V16 §83). No inventes tu propia lógica de corte de edad.
- El agente **Enrollment** (`.claude/agents/enrollment.md`, V16 §79) es el único con permiso para decidir elegibilidad — si en esta sesión sientes la tentación de que otro agente (ej. Backend genérico) decida un caso de admisión sin pasar por este agente, deténte.
- Decisión de negocio ya resuelta (V17 §88): normativa base **MEN Colombia** para `curriculum_standards.py` — no la vuelvas a preguntar, aunque en esta sesión `curriculum_standards.py` todavía no exista como módulo (llega en la sesión de `colegio_virtual_curriculum`); por ahora, deja la referencia a estándar como un campo de texto validado contra una lista de configuración vacía/placeholder, no inventes estándares reales.

**Alcance de esta sesión**:
1. `DISCOVER`+`SPECIFY`: requisitos `REQ-ADMISSIONS-XXXX` — solicitud de admisión, documentos requeridos, verificación de elegibilidad, matrícula formal, lista de espera cuando no hay cupo.
2. `IMPLEMENT`: `application_intake.py`, `eligibility_check.py` (código ya dado), `enrollment_service.py`, `waitlist_manager.py`.
3. `IMPLEMENT`: cada decisión de admisión (aceptada/rechazada/lista de espera) pasa por `record_audit_event()` con el `reason` exacto de `EligibilityResult` — nunca un registro de auditoría que diga solo "rechazado" sin el motivo.
4. `SECURITY`: RLS sobre la tabla de solicitudes de admisión (dato de menor, tenant = colegio) — reutiliza el patrón ya construido en `audit_rls`, no lo reimplementes.
5. `UNIT_TEST`: el caso de borde de `check_age_eligibility()` (niño dentro del margen de tolerancia) ya tiene prueba de referencia en V16 — complétala con fixtures reales y agrega el caso simétrico (fuera del margen, rechazo directo sin revisión).
6. `QA`: prueba explícita de que una solicitud sin cupo disponible entra a `waitlist_manager.py` en vez de fallar o perderse.

**Qué NO hacer en esta sesión**:
- No implementes `curriculum/`, `gradebook/`, `virtual_classroom/` ni `proctoring/` — dependen de que admisiones exista primero.
- No inventes normativa de edad por grado si no está en la configuración — dejarla como parámetro configurable vacío es correcto; adivinar un número no lo es.
- No conectes pagos de matrícula todavía (aunque `payments/` ya existe) — es una integración de una sesión posterior, mantén el alcance acotado.

Al terminar: mismo resumen de siempre — gates que pasaron, archivos creados, preguntas abiertas — más confirmación explícita de que ninguna decisión de elegibilidad quedó sin `reason` en el audit_log.
