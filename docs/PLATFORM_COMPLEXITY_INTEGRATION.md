# Integracion de plataformas de alta complejidad

## Propósito

Este documento incorpora al ciclo de agentes los activos de VerifiQ y Pizarra Inteligente. Ambos deben tratarse como dominios de alta complejidad, con límites de confianza, contratos y gates propios. Ningún agente debe declarar un módulo terminado solo porque exista documentación o una carpeta.

## Inventario verificado

### VerifiQ

Ubicación: `verifiq-backend/`

Es un backend FastAPI independiente con:

- KYC y liveness mediante adapters.
- RENIEC/SUNAT y AML/PEP.
- Firma electrónica simple, hash y re-firma versionada.
- Pagos, exchange rate y notificaciones.
- Uploads y storage.
- API keys, rate limiting, CORS configurable y readiness para aliados.
- Audit log con cadena de hashes y migraciones Alembic.

Límite de integración: VerifiQ no se importa dentro de `backend/app`. Se integra mediante API/adapters versionados. Sus proveedores externos permanecen mock hasta disponer de credenciales, contratos y revisión legal.

Gates mínimos para agentes:

- No exponer API keys ni secretos en logs.
- No declarar KYC, AML, biometría o firma certificada real cuando el adapter está en modo mock.
- Mantener idempotencia en firmas, KYC y pagos.
- Verificar cadena de auditoría y aislamiento por `client_id`.
- Ejecutar `verifiq-backend/tests/` antes de marcar una tarea.

Estado de verificación: la suite pasa en el entorno aislado
`verifiq-backend/.venv311`, porque las versiones fijadas requieren un runtime
compatible con Python 3.11. El Python 3.14 global no debe usarse para validar
este servicio: `psycopg2-binary` y `pydantic-core` intentan compilar allí.

### Pizarra Inteligente

Fuentes disponibles en este workspace:

- `01_documentos_maestros/PIZARRA_INTELIGENTE_ALTA_INGENIERIA.md`
- `02_auditoria/AUDITORIA_CONSISTENCIA_ERP_PIZARRA.md`
- `03_prompts_arranque/PROMPT_ARRANQUE_PIZARRA_*.md`

No se encontró un backend fuente de Pizarra separado en la raíz del workspace. Por tanto, los agentes deben tratar la Pizarra como **especificación pendiente de implementación**, no como módulo construido.

### Prototipo externo Pizarra Maestro 3D

Activo verificado: `D:\pizarra_maestro_3d.html` (27,535 bytes, actualizado
2026-09-07).

Capacidades observadas en el archivo:

- escena 3D Three.js con sólidos editables visualmente y rotación/zoom;
- fórmulas KaTeX y cálculo interactivo de volumen;
- pipeline local simulado `context_agent -> pedagogical_agent -> ui_compiler_agent`;
- historial de decisiones y filtros por acción;
- feed de agentes y entrada de profesor;
- indicador CRDT y gestos declarados honestamente como simulados.

Clasificación: **prototipo frontend avanzado**, no backend de producción. No
debe marcarse como CRDT real, cámara real, LLM real ni colaboración multiusuario
hasta que exista el servicio correspondiente y una prueba de integración.
Su contrato útil para agentes es: el pipeline debe conservar trazabilidad de
fragmento, tema, confianza, decisión, payload visual y `session_id`; la
conversión visual debe seguir siendo reversible y confirmable por el usuario.

La arquitectura documentada exige:

- Edge/offline buffer y sincronización CRDT.
- Sketch-to-vector reversible y con confirmación humana.
- Reconocimiento matemático explicable.
- Colaboración multiusuario con resolución de conflictos.
- Grabación, beamforming, accesibilidad y resiliencia.
- Privacidad de menores, consentimiento y RLS multi-tenant.
- Separación entre tooling de construcción y locks de runtime.

Gates mínimos para agentes:

- Nunca copiar un CRDT sin contrato de interoperabilidad.
- Nunca convertir trazos automáticamente sin confirmación y reversibilidad.
- Nunca activar cámara, audio o dataset de menores sin consentimiento verificable.
- Toda colaboración debe tener tenant, room y actor identificables.
- Un fallo de sincronización debe producir modo degradado explícito y evidencia.

## Reglas de interacción entre agentes

1. `DiscoveryAgent` verifica que exista el código o marca la especificación como pendiente.
2. `PlanningAgent` separa contratos compartidos de implementaciones por producto.
3. `BackendAgent` no cruza imports entre `verifiq-backend`, `backend` y tooling.
4. `SecurityAgent` revisa secretos, tenancy, consentimiento, auditoría y proveedores mock.
5. `QualityAgent` ejecuta las suites del producto afectado.
6. `ReviewAgent` bloquea afirmaciones de producción cuando hay mocks o documentación sin código.
7. `RepairAgent` crea una tarea trazable con el fallo exacto.
8. `VerificationAgent` solo permite completar cuando existe evidencia ejecutable.

## Complejidad y orden

Orden recomendado:

1. Contratos de plataforma: identidad, auditoría, tenancy, locks y eventos.
2. ERP core y módulos educativos.
3. VerifiQ como servicio regulado aislado.
4. Pizarra como producto de tiempo real con edge, CRDT y multimedia.
5. Integraciones entre productos mediante APIs versionadas, eventos idempotentes y trazas correlacionadas.

La complejidad no se resuelve creando más archivos: cada módulo debe tener propietario, contrato, prueba, gate de seguridad y evidencia de ejecución.
