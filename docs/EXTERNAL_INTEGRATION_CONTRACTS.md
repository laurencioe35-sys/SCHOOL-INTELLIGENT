# Contratos externos y prerequisitos de produccion

Este documento separa los contratos internos que ya puede implementar el ERP de
los datos que solo puede entregar cada proveedor. No se inventan firmas,
versiones, URLs, nombres de plantillas ni payloads regulatorios.

## Regla comun

Cada integracion productiva debe aportar:

- proveedor, entorno y version contractual;
- URL base y endpoints oficiales;
- autenticacion, rotacion y expiracion de secretos;
- payloads de solicitud y respuesta con vectores reales;
- firma/verificacion del webhook;
- idempotency key y ventana de reintento;
- estados terminales y transiciones permitidas;
- timeouts, rate limits, retries y circuit breaker;
- contacto operativo y procedimiento de rollback;
- evidencia de sandbox y aprobacion de produccion.

Sin esos datos la tarea permanece `BLOCKED`, no se sustituye por un mock.

## Pagos Colombia: Nequi y PSE

Contrato interno ya definido por `PaymentGateway`:

- `charge(ChargeRequest) -> ChargeResult` siempre conserva `tenant_id` en el caso de uso.
- Un cobro asincrono inicia en `pending`.
- Solo un webhook autenticado puede cambiarlo a `paid`, `failed` o `expired`.
- El evento debe ser idempotente antes de modificar factura o contabilidad.
- La conciliacion debe crear un asiento balanceado y auditable.
- `refund` requiere endpoint y reglas oficiales del proveedor.

Bloqueo externo: firma, headers, version, payload, credenciales y vectores de
Nequi/PSE no están entregados en la documentación actual.

## Meta y WhatsApp

Contrato interno:

- verificar `X-Hub-Signature-256` con el app secret;
- reclamar el `event_id` con TTL de siete días antes de efectos secundarios;
- validar tenant y destinatario antes de enviar;
- usar solo templates aprobados;
- auditar opt-in, envio, entrega, error y reintento;
- separar notificacion de factura del flujo transaccional principal.

Bloqueo externo: app de producción, webhook verificado, nombre/version de
plantilla aprobada y credenciales Meta.

## Transcripcion y agentes

Contrato interno del stream `class:transcript:chunks`:

```json
{
  "type": "transcript_chunk",
  "session_id": "class-uuid",
  "tenant_id": "tenant-uuid",
  "actor_user_id": "user-uuid",
  "raw_text": "texto verificado del proveedor STT",
  "priority": "urgent|high|normal|low",
  "provider_event_id": "idempotency-key"
}
```

El worker publica resultados en `class:agent:results`. El productor debe aportar
captura de audio autorizada, proveedor STT, política de retención y garantía de
orden/idempotencia. No se publican eventos sintéticos.

## Pizarra, HWR y audio

Requisitos de entrada antes de implementar producción:

- dataset consentido con ground truth y versión;
- modelo ONNX y labels versionados;
- matriz de confusión y umbrales de aceptación;
- hardware MEMS, geometría, calibración, AEC y grabaciones autorizadas;
- benchmark STT con SNR, WER, latencia p95 y condiciones de aula;
- política de borrado, consentimiento y auditoría.

## VerifiQ regulado

Requisitos antes de activar producción:

- proveedor KYC/biometría contratado;
- RENIEC/SUNAT o intermediario autorizado;
- proveedor AML/PEP con contrato y listas aplicables;
- PSC/TSA y perfil de firma certificado;
- claves de producción en secret manager;
- aprobación legal/regulatoria y vectores de prueba.

El `.env` de `verifiq-backend` pertenece a este servicio separado y no configura
el ERP educativo colombiano.
