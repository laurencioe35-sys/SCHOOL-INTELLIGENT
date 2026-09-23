# Prompt de arranque — Módulo de Auditoría y Row-Level Security (tercer módulo real)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 del Apéndice A antes de cada commit — es el gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

Mismo repositorio. Contabilidad y Pagos ya existen y dependen de que esta capa quede sólida — ambos módulos ya invocan `record_audit_event()` y asumen aislamiento por tenant, pero hasta ahora eso corre "con confianza" — esta sesión es la que lo hace exigible de verdad, a nivel de base de datos.

---

## PROMPT

Lee `CLAUDE.md`. Revisa `backend/app/modules/accounting/` y `backend/app/modules/payments/` — ambos ya llaman a `record_audit_event()`, pero la tabla `audit_log` y el Row-Level Security que la protegen todavía no se han implementado como pieza propia. Esta sesión los construye y **retroactivamente verifica que Contabilidad y Pagos ya la usan correctamente** — no es un módulo aislado, es la capa que sostiene a los dos anteriores.

**Objetivo de esta sesión**: implementar `audit_log` inmutable + Row-Level Security multitenant, y usarlos para **auditar** (en el sentido literal) que Contabilidad y Pagos no tienen huecos.

**Lo que el contrato YA resolvió — impléméntalo tal cual**:
- Migración de `audit_log` con los triggers `prevent_audit_log_mutation` (bloquea UPDATE/DELETE a nivel de PostgreSQL, no solo de permisos de aplicación) — está completa en `CLAUDE.md`.
- `backend/app/core/audit.py` con `record_audit_event()` — único punto de escritura permitido.
- Row-Level Security: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` + `CREATE POLICY tenant_isolation_*` + `TenantContextMiddleware` que fija `SET app.current_tenant_id` por request — todo especificado.
- `policies/audit_critical_entities.yaml` con la lista ya definida: `invoices`, `journal_entries`, `payroll_runs`, `user_roles`, `permissions`, `payment_transactions`, `inventory_adjustments`, `chart_of_accounts`.
- Segregación de funciones: `permission_check.py` con `_enforce_segregation_of_duties()` — quien crea una factura/asiento no puede aprobarlo, verificado contra el `audit_log` real, no contra el rol declarado.

**Alcance de esta sesión**:
1. `IMPLEMENT`: migración de `audit_log` + RLS sobre las 8 tablas de `audit_critical_entities.yaml` que ya existan en el repo (probablemente `invoices`, `journal_entries`, `chart_of_accounts`, `payment_transactions` — las que Contabilidad/Pagos ya crearon; el resto se marca como pendiente para cuando exista esa tabla).
2. `IMPLEMENT`: `TenantContextMiddleware` conectado al middleware de autenticación existente.
3. **Auditoría retroactiva real** (esto es lo distinto de esta sesión): revisa cada `INSERT`/`UPDATE` que Contabilidad y Pagos ya escribieron en sesiones anteriores — ¿todos pasan por `record_audit_event()` en la misma transacción que el cambio de negocio? Si encuentras un lugar donde no, es un defecto de las sesiones anteriores — créalo como tarea `REPAIR` (sección 3 del contrato) y corrígelo, no lo ignores por "no ser parte del alcance original".
4. `SECURITY`: implementa y corre las pruebas ya especificadas — `test_segregation_of_duties.py` (creador no puede aprobar su propia factura) y una prueba nueva: con RLS activo, un usuario del tenant A no puede leer una factura del tenant B ni con una query directa que "olvide" el filtro de tenant.
5. Gate G19 (auditoría inmutable) y el gate de RLS de la sección 46 del contrato: evidencia de que un intento de `UPDATE`/`DELETE` directo sobre `audit_log` falla con excepción, no en silencio.

**Qué NO hacer en esta sesión**:
- No implementes RLS sobre tablas que todavía no existen (`payroll_runs`, `user_roles`, etc.) — solo las que Contabilidad/Pagos ya crearon. Documenta las demás como pendientes explícitos.
- No toques la lógica de negocio de Contabilidad/Pagos, solo envuélvela con auditoría/RLS y corrige lo que encuentres roto en el paso 3.

Al terminar: mismo resumen de siempre, y agrega explícitamente la lista de tablas con RLS pendiente para cuando existan (payroll, users/roles).
