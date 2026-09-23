# Prompt de arranque — Integraciones Meta: WhatsApp/Facebook/Instagram (sexto módulo real del ERP)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 del Apéndice A antes de cada commit — es el gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

Mismo repositorio `erp-enterprise/`. Requiere Auditoría/RLS (los tokens externos y los webhooks deben auditarse igual que cualquier otra operación sensible) y, si vas a notificar facturas por WhatsApp, Contabilidad/Pagos ya deben existir para tener algo real que notificar.

---

## PROMPT

Lee `CLAUDE.md`, específicamente la sección de `integrations_social/` y `token_vault.py`. Esta sesión toca la superficie de mayor "radio de explosión" del ERP hasta ahora — un token de Meta comprometido no es un bug aislado, es acceso a mensajería de clientes reales. Trátala con ese nivel de cuidado desde el primer commit, no como "otra integración más".

**Objetivo de esta sesión**: implementar WhatsApp Business Cloud API completo (el caso de uso con ROI más claro: notificación de facturas/cobranza) y dejar Facebook/Instagram como stubs con la misma interfaz, para una sesión posterior.

**Lo que el contrato YA resolvió — impléméntalo tal cual, en este orden de dependencia**:
1. `token_vault.py` — envelope encryption (data key + clave maestra), nunca expone el valor en logs/`repr`. Esto va PRIMERO — ningún token de WhatsApp se guarda sin pasar por aquí, ni siquiera "temporalmente para probar".
2. `meta_webhooks/signature_verifier.py` — `hmac.compare_digest`, comparación de tiempo constante.
3. `meta_webhooks/idempotency_store.py` — TTL de 7 días, reutiliza Redis ya configurado.
4. `whatsapp/opt_in_registry.py` — **este va antes que `whatsapp/client.py`**, no después: ningún mensaje sale sin verificar opt-in registrado, así que si lo implementas al final "para no bloquear las pruebas", vas a terminar probando envíos sin la verificación real puesta, y es fácil que se quede así.
5. `whatsapp/client.py` + `whatsapp/session_window.py` — envío dentro de la ventana de 24h, plantillas solo por nombre exacto aprobado (nunca contenido libre fuera de la ventana).
6. `whatsapp/templates_registry.py` — con `approved=False` por defecto; el contrato ya advierte que el contenido real de cada plantilla lo apruebas tú directamente con Meta, así que **no inventes texto de plantilla** — deja el registro con placeholders y `approved=False` hasta que confirmes la aprobación real.

**Alcance de esta sesión**:
1. `IMPLEMENT` los 6 puntos anteriores, en ese orden — el orden importa más que en sesiones anteriores porque cada uno depende de que el anterior ya bloquee lo que debe bloquear.
2. `IMPLEMENT`: conecta un caso de uso real — cuando una factura pasa a `overdue` (Contabilidad) o un pago falla (Pagos), dispara un intento de notificación WhatsApp usando `invoice_notification` como plantilla — pero como `approved=False` por defecto, el sistema debe **loguear la intención y no enviar nada**, con un mensaje claro de por qué no envió. No hagas que "no hay plantilla aprobada" sea un error silencioso ni una excepción que tumbe el flujo de facturación — factura y notificación son procesos desacoplados.
3. `SECURITY`: gate G18 del contrato — prueba de que un webhook con firma inválida se rechaza con 401 ANTES de tocar el payload, y prueba de idempotencia (mismo evento dos veces → segunda vez no reprocesa).
4. `SECURITY`: prueba del `opt_in_registry` — intento de envío a un número sin opt-in registrado debe fallar explícito, no "enviar de todos modos porque ya teníamos el número guardado de antes".
5. `IMPLEMENT`: Facebook e Instagram como clases que implementan la misma interfaz base pero cada método lanza `NotImplementedError("Pendiente — sesión futura")` — así el módulo `integrations_social` queda con su forma completa aunque no todo esté implementado, sin fingir que funciona.

**Qué NO hacer en esta sesión**:
- No implementes Facebook Lead Ads ni Instagram DMs todavía — son casos de uso distintos (marketing/mensajería social) sin relación directa con cobranza, que es el caso de uso que sí justifica esta sesión.
- No conectes esto al asistente de voz — son capas independientes que comparten solo el patrón de auditoría, no lógica.
- No redactes tú el texto de ninguna plantilla de WhatsApp pensando que "es solo un ejemplo" — un ejemplo mal etiquetado tiende a terminar en producción. Dejar `approved=False` y el cuerpo vacío es la opción segura.

Al terminar: mismo resumen de siempre, más confirmación explícita de que probaste el caso de "plantilla no aprobada" y el sistema no truena ni envía nada — es la prueba que demuestra que el desacople factura/notificación funciona de verdad.
