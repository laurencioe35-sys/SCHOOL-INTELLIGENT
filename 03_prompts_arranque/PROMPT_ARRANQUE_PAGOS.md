# Prompt de arranque — Módulo de Pagos (segundo módulo real)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 del Apéndice A antes de cada commit — es el gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

Usa el mismo repositorio de la sesión de Contabilidad. `CLAUDE.md` ya está en la raíz. Esta sesión asume que el módulo de Contabilidad (`journal_entries`, `chart_of_accounts`) ya existe y pasó sus gates — Pagos depende de poder generar un asiento contable automático al conciliar.

---

## PROMPT

Lee `CLAUDE.md` (ya lo conoces de la sesión anterior) y el estado actual de `backend/app/modules/accounting/` antes de empezar — Pagos se conecta directo a ese módulo, no es independiente.

**Objetivo de esta sesión**: construir el módulo de **Pagos** completo — pasarela adaptadora + conciliación — siguiendo el mismo loop autónomo de la sesión anterior (DISCOVER→...→COMMIT), sin saltar pasos.

**Lo que el contrato YA resolvió — impléméntalo tal cual, no lo rediseñes**:
- `backend/app/modules/payments/gateway_interface.py` — el contrato `PaymentGateway` (charge/refund/verify_webhook_signature) está completo en `CLAUDE.md`.
- `providers/stripe.py` — implementación de referencia completa, cópiala tal cual y luego replica el mismo patrón para los demás proveedores.
- `reconciliation/matcher.py` — la función `reconcile_payment()` ya resuelve los 6 casos borde documentados (duplicado, parcial, sobrepago, un pago a varias facturas, moneda distinta, sin factura asociable). No reescribas esta lógica desde cero — impléméntala exactamente como está.
- `webhooks/webhook_router.py` y `idempotency_store.py` — verificación de firma de tiempo constante + idempotencia por TTL, ya especificados.
- Locking: usa `backend/app/platform/concurrency/resource_lock.py` (NO el tooling de `agents/runtime/` — esa separación fue una corrección explícita documentada en `AUDITORIA_CONSISTENCIA_ERP_PIZARRA.md`, no la repitas mal).

**Alcance de esta sesión**:
1. `DISCOVER`+`SPECIFY`: requisitos `REQ-PAYMENTS-XXXX` para: cobrar con Stripe, recibir webhook, conciliar contra una factura existente, generar el asiento contable automático en `journal_entries` cuando el pago se aplica.
2. `IMPLEMENT`: solo **Stripe** como proveedor real en esta sesión (los demás proveedores — Nequi, PSE, Wompi, MercadoPago, PayU, PayPal — quedan como stub que implementa la interfaz pero lanza `NotImplementedError` explícito, para la siguiente sesión). No implementes 7 pasarelas a la vez — es la forma de que esto se caiga por alcance excesivo, no por dificultad técnica.
3. `IMPLEMENT`: el punto de conexión con Contabilidad es literal — cuando `reconcile_payment()` marca una factura como `PAID`/`PARTIALLY_PAID`, debe crear un `journal_entry` real (débito a caja/banco, crédito a cuentas por cobrar) usando `assert_balanced()` del módulo de Contabilidad ya construido. Si esa conexión no queda funcionando de punta a punta, la sesión no está terminada aunque cada módulo individual pase sus pruebas por separado.
4. `UNIT_TEST`+`INTEGRATION_TEST`: los 6 casos borde de `matcher.py` (ya están como esqueleto de test en el contrato) deben quedar completos con fixtures reales, no solo la firma de la función.
5. `SECURITY`: gate G23 del contrato — cero número de tarjeta completo en logs/DB, tokenización confirmada, firma de webhook verificada con `hmac.compare_digest`.

**Qué NO hacer en esta sesión**:
- No implementes las otras 6 pasarelas de pago todavía.
- No toques el frontend.
- No inventes el contenido de plantillas de WhatsApp ni nada de integraciones-social — no tiene relación con Pagos.

**Antes de cerrar la sesión**: prueba de punta a punta manual (o E2E automatizada si el tiempo lo permite) — simular un webhook de Stripe de pago aprobado y verificar que: (1) la factura queda en `PAID`, (2) existe un `journal_entry` balanceado en Contabilidad, (3) el evento quedó en `audit_log`. Si alguno de los 3 falla, la integración entre módulos no está completa.

Al terminar, dame el mismo resumen que la sesión anterior: gates que pasaron, archivos creados, preguntas abiertas para la siguiente sesión (candidatos naturales: implementar Nequi/PSE para el mercado colombiano, o el módulo de Auditoría/RLS que ambos módulos ya dependen de tener listo).
