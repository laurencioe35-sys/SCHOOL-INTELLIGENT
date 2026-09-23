# Prompt de arranque — Pizarra Inteligente: Dataset de Entrenamiento Consentido (segundo módulo real)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 del Apéndice A antes de cada commit — es el gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

Mismo repositorio `smart-whiteboard/`. Requiere que la sesión de Sketch-to-Vector ya exista (el clasificador por reglas debe estar funcionando solo, sirviendo de fallback) — esta sesión NO reemplaza ese fallback, construye el camino para eventualmente tener un modelo entrenado real, sin comprometer la privacidad de los niños que generan el trazo.

---

## PROMPT

Lee `CLAUDE.md` (la Pizarra) — específicamente las secciones de consentimiento, pseudonimización, augmentación sintética y acuerdo entre anotadores. Esta sesión es distinta a todas las anteriores del ERP y de la Pizarra: **el criterio de éxito no es "funciona", es "no se puede usar mal aunque alguien lo intente"** — cualquier atajo que parezca razonable para tener datos más rápido casi seguro viola alguno de los puntos del análisis del contrato. Si en algún punto de esta sesión sientes la tentación de "guardar el student_id junto al trazo para hacer debugging más fácil", eso es exactamente lo que el contrato prohíbe — detente y usa el pseudónimo.

**Objetivo de esta sesión**: implementar el pipeline completo de recolección-con-consentimiento → pseudonimización → augmentación sintética → etiquetado con acuerdo entre anotadores, de modo que al final exista un corpus de entrenamiento *utilizable* sin que ningún dato identifique a un menor.

**Lo que el contrato YA resolvió — impléméntalo tal cual**:
- `dataset_collection.py` — `submit_for_training_corpus()` verifica consentimiento activo en cada aportación (no una vez al año) y pseudonimiza con hash unidireccional (`_pseudonymize`) antes de guardar.
- `revoke_consent_and_purge()` — derecho al olvido, retorna conteo real de muestras eliminadas.
- `synthetic_augmentation.py` — `augment_stroke()` con jitter geométrico, rotación leve, y simulación de temblor motriz (`simulate_motor_tremor=True`) — esto último no es opcional, es la mitigación de sesgo de accesibilidad del contrato.
- `labeling_quality.py` — `cohens_kappa()` y `MIN_ACCEPTABLE_KAPPA = 0.75` como puerta antes de incorporar un lote.

**Alcance de esta sesión**:
1. `DISCOVER`+`SPECIFY`: define el modelo de datos de `consent_records` (quién dio el consentimiento — el tutor legal, no el niño —, para qué uso específico, cuándo, y cómo se revoca) ANTES de escribir una sola línea de recolección. Sin esta tabla, `_get_active_consent()` no tiene de dónde leer.
2. `IMPLEMENT`: el flujo completo `trazo en clase → ¿hay consentimiento activo? → pseudonimizar → guardar en corpus de cuarentena` (nunca directo al set de entrenamiento "oficial" — ver punto 4).
3. `IMPLEMENT`: `revoke_consent_and_purge()` con prueba real — crea 3 muestras de un estudiante ficticio, revoca su consentimiento, verifica que las 3 desaparecen del corpus y que el conteo retornado es exactamente 3, no un booleano genérico de "éxito".
4. `IMPLEMENT`: el corpus tiene DOS estados, no uno: `quarantine` (recién pseudonimizado, sin verificar) y `training_ready` (pasó por al menos 2 anotadores con Cohen's Kappa ≥ 0.75 sobre ese lote). Un ejemplo en cuarentena NUNCA se usa para entrenar — esto es lo que cierra el gate G43, y es fácil de pasar por alto si se implementa el etiquetado como un paso "de una vez" en lugar de una puerta con dos estados explícitos.
5. `IMPLEMENT`: `augment_stroke()` conectado al pipeline — por cada ejemplo real que llega a `training_ready`, genera al menos 5 variantes sintéticas (incluyendo al menos 1 con `simulate_motor_tremor=True`) antes de que el conjunto se considere listo para entrenar.
6. `SECURITY`/`QA`: gates G42, G43, G44 del contrato, cada uno con su prueba automatizada, no con una revisión manual.

**Qué NO hacer en esta sesión**:
- No entrenes el modelo ONNX todavía — esta sesión construye el dataset, no el entrenamiento. El modelo entrenado (`shape_classifier_v1_labels.json` + el `.onnx` real) es una sesión posterior, cuando el corpus `training_ready` tenga suficiente volumen.
- No conectes esto a ningún panel físico en producción real todavía — usa datos simulados/sintéticos para probar el pipeline de consentimiento-pseudonimización de punta a punta, sin necesidad de una escuela real conectada.
- No implementes la recolección de video/rostro (biometría) — esta sesión es solo trazo geométrico (x,y,presión,t), que es un dato de mucho menor riesgo; la biometría, si algún día se activa, es una sesión completamente distinta con su propio análisis de consentimiento.

Al terminar: mismo resumen de siempre, más un dato específico obligatorio: cuántas muestras sintéticas se generaron por cada muestra real consentida (debe ser ≥5, y al menos una con temblor simulado), y confirma con una prueba concreta que el derecho al olvido funciona de punta a punta, no solo que la función existe.
