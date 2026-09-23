# Prompt de arranque — Asistente de Voz + Guardarraíl de Confidencialidad (quinto módulo real)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 del Apéndice A antes de cada commit — es el gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

Mismo repositorio. Requiere que Auditoría/RLS y al menos Contabilidad ya existan — este módulo es, literalmente, una capa de acceso alternativa (voz) a datos que ya tienen su capa de permisos por pantalla. Si esa capa de permisos no existe todavía de verdad, este módulo no tiene nada que reforzar.

---

## PROMPT

Lee `CLAUDE.md`. Revisa `backend/app/core/permissions.py` (o donde haya quedado el motor RBAC/ABAC de la sesión de Auditoría/RLS) — el guardarraíl de voz de esta sesión **reutiliza ese motor, no crea uno paralelo**. Si esta sesión te tienta a escribir una segunda función de "verificar permiso" específica para voz, deténte — es exactamente el error que el contrato marca como punto 3 del análisis de `permission_check.py`: la voz nunca puede ser un canal más permisivo que la pantalla, y la única forma de garantizar eso es que sea *el mismo código*, no una copia paralela.

**Objetivo de esta sesión**: implementar el asistente de voz — STT/TTS + guardarraíl de confidencialidad + redacción campo por campo — sobre los módulos de negocio que ya existen (Contabilidad como primer caso de uso real: "¿cuál es el saldo de la cuenta X?").

**Lo que el contrato YA resolvió — impléméntalo tal cual**:
- `voice_assistant/stt/` y `tts/` con patrón adaptador (Whisper self-hosted por defecto, con interfaz para swap a proveedor gestionado).
- `voice_assistant/confidential_guard/permission_check.py` — llama al motor de permisos ya existente (Auditoría/RLS), nunca lo reimplementa.
- `voice_assistant/confidential_guard/redaction_rules.py` — reglas campo por campo (`VOICE_FIELD_RULES`), ya con ejemplos (`account_number` bloqueado, `net_salary` con confirmación extra).
- `voice_assistant/confidential_guard/audit_hook.py` — cada consulta confidencial por voz escribe en el mismo `audit_log` inmutable de la sesión de Auditoría, con `source_channel="voice"`.

**Alcance de esta sesión**:
1. `IMPLEMENT`: pipeline completo `audio → STT → intent_router → consulta real a Contabilidad → permission_check (reutilizado) → redaction_rules → TTS → audio`. El "consulta real" es la parte que no puedes saltarte: el asistente de voz **nunca** debe inventar una cifra — si no puede consultar el dato real, debe decir que no puede responder, no aproximar.
2. `IMPLEMENT`: `VoiceOrb.tsx` + `PushToTalkButton.tsx` en el frontend, conectados al `DegradedModeManager`-equivalente del ERP (si no existe todavía en el ERP, créalo con la misma lógica que el de la Pizarra Inteligente: la app nunca debe "morir" si STT/TTS no responde, debe degradar a mostrar un aviso y seguir funcionando por texto).
3. `SECURITY`: prueba obligatoria (ya está como esqueleto en el contrato) — `test_voice_channel_cannot_bypass_screen_restriction`: un rol sin acceso de lectura a nómina no puede obtenerlo pidiéndolo por voz, aunque la pregunta esté fraseada distinto a como se vería en pantalla.
4. `SECURITY`: prueba nueva de esta sesión — un usuario pide por voz un dato que su rol SÍ puede ver en pantalla pero que está en `VOICE_FIELD_RULES` como `BLOCK` (ej. número de cuenta completo) → debe negarse por voz aunque el permiso de pantalla exista.

**Qué NO hacer en esta sesión**:
- No implementes el avatar 3D todavía (sección de Avatar del contrato) — es una capa visual opcional y desacoplada; el asistente de voz debe funcionar completo sin él primero.
- No conectes WhatsApp/Meta en esta sesión — son integraciones externas sin relación con el guardarraíl de confidencialidad interno.
- No apliques `revoke_consent_and_purge` ni nada del corpus de entrenamiento de reconocimiento — eso es específico del proyecto de la Pizarra Inteligente, no de este asistente de voz basado en STT/TTS genérico.

Al terminar: mismo resumen de siempre, y confirma explícitamente con qué prueba verificaste que la voz nunca fue más permisiva que la pantalla — esa es la evidencia central de esta sesión, no un detalle secundario.
