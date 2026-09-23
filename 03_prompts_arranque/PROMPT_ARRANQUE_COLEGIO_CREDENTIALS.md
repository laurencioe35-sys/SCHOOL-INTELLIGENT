# Prompt de arranque — Colegio Virtual: Historial Académico y Certificados (credentials/)

> **Rige el Apéndice A de CLAUDE.md**: ningún archivo se fusiona por compacidad. Gate G47 antes de cada commit.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: vive como `colegio_virtual_credentials` en `module_backlog.yaml`, gates G57-G60.

Mismo repositorio. Requiere `colegio_virtual_gradebook` completo — no hay historial ni certificado sin boletines ya firmados de verdad.

---

## PROMPT

Lee `CLAUDE.md`, Adenda V19 (`transcript_service.py`, código+prueba completos) y V20 (`certificate_generator.py` + `certificate_signature.py`, código+prueba completos). Esta sesión, como la de Gradebook, no diseña lógica nueva — **ensambla y prueba de punta a punta** dos documentos de consecuencia creciente: el historial (interno/transferencia) y el certificado de graduación (la decisión de mayor peso de todo el vertical).

**Objetivo**: implementar los 2 archivos ya dados, más la persistencia (`_load_signed_report_cards`, `_load_certificate_status`, etc. — quedaron con `NotImplementedError` o comentarios de "omitido" en el contrato, son responsabilidad tuya completarlos siguiendo el modelo de datos ya definido en secciones anteriores, no inventar un esquema paralelo).

**Alcance**:
1. `IMPLEMENT`: `transcript_service.py` tal cual (V19) — verifica con una prueba real que un boletín sin firma se omite del documento pero SÍ queda auditado (no en silencio total).
2. `IMPLEMENT`: `certificate_generator.py` + `certificate_signature.py` tal cual (V20).
3. `SECURITY`: gate **G59** — escribe la prueba de que `AUTHORIZED_GRADUATION_SIGNER_ROLES` (`principal`, `rector`) es un conjunto **distinto y más estrecho** que `AUTHORIZED_SIGNER_ROLES` de boletines (`academic_coordinator`, `principal`) — si en tu implementación terminan siendo el mismo set, es una violación real de V20 §97 punto 2, corrígelo antes de commit.
4. `SECURITY`: gate **G60** — prueba de que `revoke_certificate()` nunca borra el registro `CREATE`/`APPROVE` original, solo agrega un evento `UPDATE` con el nuevo estado.
5. `QA`: implementa `verify_certificate_publicly()` como endpoint sin autenticación de sesión (es para terceros externos) pero con rate limiting — un certificado no es información secreta, pero tampoco debe poder scrapearse en masa.

**Qué NO hacer**: no agregues campos nuevos a `TranscriptEntry` que expongan más de lo que un historial legítimamente contiene (proctoring, comunicación con acudientes) — esa restricción es de diseño del tipo, no un filtro que se pueda "agregar después si hace falta".

Al terminar: resumen de siempre + confirmación explícita de que probaste emitir un certificado a un estudiante que NO cumple requisitos y el sistema lo rechazó con el detalle exacto de qué curso falta — no solo "no puede graduarse".
