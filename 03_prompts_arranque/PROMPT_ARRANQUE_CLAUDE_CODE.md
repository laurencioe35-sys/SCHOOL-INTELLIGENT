# Prompt de arranque — Módulo de Contabilidad (primer módulo real)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 del Apéndice A antes de cada commit — es el gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

1. Crea el repositorio vacío `erp-enterprise/`.
2. Copia estos 3 archivos a la raíz del repo:
   - `ERP_ENTERPRISE_AUTONOMO_V2_ROBUSTO.md` → renómbralo a `CLAUDE.md`
   - `AUDITORIA_CONSISTENCIA_ERP_PIZARRA.md` → déjalo como referencia en `docs/`
   - Este mismo prompt, si quieres guardarlo como `docs/00-product/kickoff-accounting.md`
3. Abre Claude Code en esa carpeta y pega el prompt de abajo.

---

## PROMPT

Este repositorio tiene un archivo `CLAUDE.md` en la raíz — es el contrato maestro de arquitectura del proyecto. Léelo completo antes de escribir una sola línea de código. También hay un archivo `AUDITORIA_CONSISTENCIA_ERP_PIZARRA.md` en `docs/` con dos correcciones de nomenclatura ya resueltas (nombres de paquete Python en snake_case, y separación entre `agents/runtime/` como tooling de construcción vs. `backend/app/platform/` como librería de producto) — respétalas desde el primer commit, no las repitas como error.

**Objetivo de esta sesión**: construir el primer módulo de negocio real y completo — **Contabilidad** — siguiendo el loop autónomo descrito en la sección 3 del contrato (DISCOVER → SPECIFY → PLAN → IMPLEMENT → STATIC_CHECK → UNIT_TEST → INTEGRATION_TEST → E2E → SECURITY → PERFORMANCE → REVIEW → [ARBITRATE] → REPAIR → VERIFY → CHECKPOINT → COMMIT). No saltes pasos del loop aunque parezca obvio.

**Decisiones de negocio ya tomadas — no las vuelvas a preguntar** (documentadas en el contrato, sección "Decisiones resueltas como recomendación por defecto"):
- Norma contable: PUC Colombia + NIIF para Pymes.
- Entidades bajo auditoría estricta (segregación de funciones): `invoices`, `journal_entries`, `payroll_runs`, `user_roles`, `permissions`, `payment_transactions`, `inventory_adjustments`, `chart_of_accounts`.

**Alcance de esta sesión (no más que esto)**:
1. `DISCOVER` + `SPECIFY`: convierte los requisitos de contabilidad del contrato en entradas `REQ-ACCOUNTING-XXXX` en `REQUIREMENTS.md`, siguiendo el esquema de requisito de la sección 4.1 (criterios INVEST, NFR cuantificados, trazabilidad). Empieza por: crear cuenta contable, registrar asiento manual, cerrar periodo, consultar balance de comprobación.
2. `PLAN`: confirma que el plan es compatible con el modelo de datos ya definido en el contrato (`chart_of_accounts`, `accounting_periods`, `journal_entries`, `journal_entry_lines` — están con SQL completo, migración de Alembic y triggers de inmutabilidad de periodo cerrado). No rediseñes ese esquema desde cero, ya está resuelto — impleméntalo tal cual.
3. `IMPLEMENT`:
   - Migraciones Alembic de las 4 tablas (ya tienes el SQL en el contrato — cópialo, no lo reinventes).
   - `backend/app/modules/accounting/services/journal_entry_service.py` con `assert_balanced()` (ya está en el contrato).
   - Endpoints REST mínimos: crear cuenta, crear asiento, listar balance de comprobación por periodo.
   - Conecta `record_audit_event()` (ya definido en el contrato, sección de `audit_log`) a cada creación/edición de asiento — no es opcional, es gate G6/G19.
4. `UNIT_TEST` + `INTEGRATION_TEST`: incluye explícitamente los 4 casos del análisis previo de `chart_of_accounts` en el contrato (ciclo en la jerarquía, periodo cerrado, cuenta agregadora sin postings, partida doble balanceada por moneda) — son pruebas ya especificadas, no las omitas.
5. `SECURITY`: aplica Row-Level Security de la sección correspondiente del contrato sobre estas 4 tablas.
6. Antes de `COMMIT`: verifica los gates G0, G2, G4, G6, G7, G19 contra la lista de la sección 12 del contrato original y confirma cada uno con evidencia, no de palabra.

**Qué NO hacer en esta sesión**:
- No toques frontend todavía.
- No implementes pagos, WhatsApp, voz, ni ningún otro módulo — solo contabilidad.
- No inventes reglas contables que el contrato no definió — si algo no está resuelto, créalo como pregunta abierta en `docs/11-requirements-engineering/risk-register.md`, no lo decidas solo.

Al terminar, dame un resumen de: qué gates pasaron, qué archivos se crearon, y qué quedó como pregunta abierta para la siguiente sesión.
