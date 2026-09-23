# Prompt de arranque — Proveedores Nequi y PSE (cuarto módulo real)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 del Apéndice A antes de cada commit — es el gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

Mismo repositorio. Requiere que la sesión de Auditoría/RLS ya haya corrido (Pagos ya debe estar auditado y con RLS activo antes de agregarle más superficie).

---

## PROMPT

Lee `CLAUDE.md` y el estado actual de `backend/app/modules/payments/` (Stripe ya implementado, los demás son stubs). Esta sesión completa **Nequi** y **PSE** — los dos métodos de pago locales para el mercado colombiano, que es el mercado de referencia ya usado en las decisiones de negocio del contrato (PUC Colombia + NIIF Pymes).

**Objetivo de esta sesión**: implementar `providers/nequi.py` y `providers/pse.py` siguiendo exactamente el mismo contrato `PaymentGateway` que ya cumple `providers/stripe.py` — mismo patrón, proveedor distinto.

**Diferencias reales frente a Stripe que esta sesión debe resolver (no asumir que es "copiar y pegar")**:
1. **Nequi y PSE no tokenizan tarjeta** — son pagos por transferencia/billetera, el flujo es: generar una solicitud de cobro → el usuario aprueba desde su app Nequi o su banco → webhook de confirmación asíncrona. El método `charge()` de la interfaz debe devolver `status="pending"` de inmediato (no "approved" como Stripe con tarjeta), y la confirmación real llega minutos después por webhook — ajusta `reconciliation/matcher.py` si asume que `charge()` siempre resuelve al instante (revísalo, no lo asumas).
2. **PSE requiere selección de banco del usuario antes de generar la solicitud** — el payload de `charge()` necesita un campo adicional (`bank_code`) que Stripe no tiene; extiende el contrato con un parámetro opcional en vez de romper la interfaz para los demás proveedores.
3. **Verificación de firma de webhook**: cada proveedor colombiano tiene su propio mecanismo (no es HMAC-SHA256 genérico como Stripe necesariamente) — investiga y documenta el mecanismo real de cada uno en `docs/03-api/payments.md` antes de implementar `verify_webhook_signature()`; si el mecanismo exacto no está claro en la documentación pública del proveedor, créalo como pregunta abierta explícita en vez de adivinar un esquema de firma que no vas a poder verificar en producción.

**Alcance de esta sesión**:
1. `IMPLEMENT`: `providers/nequi.py`, `providers/pse.py` completos con manejo de estado `pending`.
2. `IMPLEMENT`: ajusta `reconciliation/matcher.py` si es necesario para que un pago en estado `pending` no se trate como `UNMATCHED` — debe quedar en un estado intermedio explícito hasta que llegue el webhook de confirmación.
3. `SECURITY`: webhook de cada proveedor con idempotencia (reutiliza `idempotency_store.py` ya construido) — un reintento de red no debe generar un pago duplicado.
4. `UNIT_TEST`+`INTEGRATION_TEST`: simula el flujo completo asíncrono — `charge()` → estado pendiente → webhook llega 2 minutos después (simulado) → factura pasa a `PAID` → asiento contable generado.

**Qué NO hacer en esta sesión**:
- No implementes Wompi/MercadoPago/PayU/PayPal todavía — un proveedor local a la vez ya fue la lección de la sesión de Pagos.
- No inventes el mecanismo de firma de webhook si no está documentado con certeza — es preferible dejarlo como pregunta abierta que como una verificación de seguridad que en realidad no verifica nada.

Al terminar: mismo resumen de siempre, más la lista de preguntas abiertas sobre firma de webhook si alguna quedó sin resolver con certeza.
