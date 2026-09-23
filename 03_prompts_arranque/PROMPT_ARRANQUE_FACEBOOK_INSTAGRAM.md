# Prompt de arranque — Facebook e Instagram: Leads y Mensajería Social (séptimo módulo real del ERP)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 del Apéndice A antes de cada commit — es el gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

Mismo repositorio `erp-enterprise/`. Requiere la sesión de WhatsApp ya completa — `token_vault.py`, `meta_webhooks/signature_verifier.py` e `idempotency_store.py` ya existen y esta sesión los reutiliza tal cual, no los reimplementa. Los archivos `facebook/client.py` e `instagram/client.py` quedaron como stubs con `NotImplementedError` — esta sesión los completa.

---

## PROMPT

Lee `CLAUDE.md`, sección de `integrations_social/facebook/` e `integrations_social/instagram/`. A diferencia de WhatsApp (un solo caso de uso: notificación transaccional), Facebook e Instagram tienen **dos casos de uso con requisitos de datos completamente distintos** — no los trates como "una integración más de mensajería":

1. **Captura de leads** (Facebook Lead Ads) — datos entrando al CRM desde afuera.
2. **Mensajería/DMs** (Facebook Page + Instagram DMs) — igual que WhatsApp, requiere opt-in y ventana de conversación.

**Lo que el contrato YA resolvió — impléméntalo tal cual**:
- `facebook/lead_ads_sync.py` — sincroniza leads hacia el CRM.
- `facebook/page_messaging.py`, `instagram/dm_inbox.py` — mensajería, mismo patrón de opt-in que WhatsApp (reutiliza `opt_in_registry.py`, que aunque está en la carpeta `whatsapp/`, su lógica de consentimiento no es específica de un proveedor — extráela a `integrations_social/opt_in_registry.py` compartido si todavía no lo está, en vez de duplicarla por proveedor).
- `facebook/catalog_sync.py`, `instagram/shopping_catalog_sync.py` — sincronización de catálogo de producto (depende de que exista un módulo de `inventory`/`sales` con productos reales — si no existe todavía en el repo, créalo como stub explícito, no inventes su forma aquí).

**Diferencia real que esta sesión debe resolver (no es "copiar WhatsApp")**:
- Un **lead de Facebook Lead Ads no es un contacto que dio opt-in para mensajería** — son dos consentimientos distintos (llenar un formulario de anuncio ≠ aceptar recibir mensajes). No conectes `lead_ads_sync.py` directo a `page_messaging.py` asumiendo que un lead ya puede recibir DM — eso sería enviar mensajería sin opt-in real, exactamente lo que la sesión de WhatsApp bloqueó a propósito.
- Instagram exige que la cuenta esté vinculada a una página de Facebook (requisito de la plataforma, no del contrato) — el flujo de conexión (`google/oauth.py` es el patrón equivalente ya construido para Google) debe verificar y guardar esa vinculación antes de permitir activar DMs de Instagram, o fallar explícito si no está vinculada.

**Alcance de esta sesión**:
1. `IMPLEMENT`: `lead_ads_sync.py` completo — un lead entra, se crea/actualiza un contacto en CRM, **sin** opt-in de mensajería activado por defecto.
2. `IMPLEMENT`: `page_messaging.py` e `instagram/dm_inbox.py` con opt-in explícito y compartido (no duplicado por proveedor).
3. `IMPLEMENT`: bandeja unificada mínima en backend — un endpoint que devuelve mensajes de WhatsApp+Facebook+Instagram mezclados y ordenados por fecha, como base de lo que el frontend (`SplitPanel`/`DockablePanel`, sección de diseño del contrato) va a consumir en una sesión futura de frontend.
4. `SECURITY`: reutiliza (no reescribe) `signature_verifier.py` e `idempotency_store.py` de la sesión de WhatsApp para los webhooks de Facebook/Instagram — si notas que necesitas un verificador "casi igual pero distinto", es señal de que deberías generalizar el existente, no crear uno paralelo.
5. `QA`: prueba explícita del punto de diferencia real: un lead recién capturado por Lead Ads, sin opt-in de mensajería, no puede recibir un DM automático — el intento debe fallar igual que un número sin opt-in falló en la sesión de WhatsApp.

**Qué NO hacer en esta sesión**:
- No implementes el catálogo de producto si `inventory`/`sales` no existen todavía en el repo — déjalo como stub explícito con `NotImplementedError`, documentado como dependencia pendiente.
- No construyas el frontend de la bandeja unificada todavía — solo el endpoint backend que la va a alimentar.
- No asumas opt-in de mensajería a partir de un lead de anuncio — es el error específico que esta sesión existe para prevenir.

Al terminar: mismo resumen de siempre, y confirma explícitamente con qué prueba verificaste que un lead sin opt-in no puede recibir mensajería automática — es la evidencia central de que las dos capas de consentimiento quedaron separadas de verdad.
