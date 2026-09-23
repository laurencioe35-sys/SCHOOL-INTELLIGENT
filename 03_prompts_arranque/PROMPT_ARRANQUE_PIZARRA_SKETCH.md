# Prompt de arranque — Pizarra Inteligente: Motor Sketch-to-Vector (primer módulo real)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún archivo/servicio/función de esta sesión se fusiona con otro por compacidad. Corre el checklist de la sección 13 del Apéndice A antes de cada commit — es el gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

Repositorio nuevo y separado del ERP: `smart-whiteboard/`. Este proyecto reutiliza módulos del ERP (voz, avatar, locking) pero es un producto distinto — no lo mezcles en el mismo repo que `erp-enterprise/`. Si necesitas el `voice_assistant` o el `resource_lock.py` del ERP, impórtalos como dependencia de un paquete compartido (`erp-platform-shared`), no copies el código ni lo vuelvas a escribir.

---

## PROMPT

Copia `PIZARRA_INTELIGENTE_ALTA_INGENIERIA.md` a la raíz de este repositorio como `CLAUDE.md`. También copia `AUDITORIA_CONSISTENCIA_ERP_PIZARRA.md` a `docs/` — el import corregido de `zone_conflict_bridge.py` (que depende de `resource_lock.py` del ERP, no del tooling de Claude Code) es vinculante desde el primer commit.

**Objetivo de esta sesión**: construir el motor de reconocimiento de forma (`sketch_engine/`) de punta a punta — es la funcionalidad central que compite directamente con la referencia china del video, así que es el candidato correcto para la primera sesión (a diferencia del ERP, donde Contabilidad era la base; aquí el reconocimiento de forma es la base de casi todo lo demás: math handwriting, avatar, analítica).

**Lo que el contrato YA resolvió — impléméntalo tal cual, en este orden de dependencia**:
1. `vectorizer.py` — clasificador por reglas (`classify_shape`, `extract_geometric_features`) — es el **fallback garantizado**, impléméntalo primero y verifícalo solo, sin el modelo entrenado todavía.
2. `vertex_templates.py` — registro extensible de formas 3D (`@register_vertex_template`) — depende de (1).
3. `shape_classifier_model.py` — wrapper ONNX con timeout 0.6s y fallback automático a (1) — depende de (1) y (2). No implementes esto sin haber verificado primero que (1) funciona solo, porque (3) debe poder caer de vuelta a (1) en cualquier momento.
4. `ShapeConfirmationPopover.tsx` — frontend, consume el resultado de (3) o (1), nunca auto-aplica una conversión con confianza < 0.75.

**Alcance de esta sesión**:
1. `IMPLEMENT` los 4 puntos anteriores, en ese orden, con gate intermedio: no pases a (3) sin que (1)+(2) tengan sus pruebas pasando.
2. `SECURITY`/`QA`: gate G39 del contrato — prueba obligatoria de forzar el fallo del modelo ONNX (archivo corrupto o ausente) y verificar que `classify_shape` responde igual, sin excepción visible al usuario. Esta prueba es más importante en esta sesión que lograr que el modelo entrenado funcione perfecto — un modelo que no existe todavía (no hay dataset real, ver sesión siguiente) es esperado; un fallback que no funciona no lo es.
3. `IMPLEMENT`: `DegradedModeManager.ts` con al menos los estados `ONLINE_FULL`/`DEGRADED_NO_AI` — la regla de oro (`canWriteFreehand()` siempre `true`) debe estar escrita y probada desde esta primera sesión, no como algo para después.
4. No implementes el modelo ONNX entrenado real todavía — no hay dataset (esa es la sesión siguiente, `PROMPT_ARRANQUE_PIZARRA_DATASET`, pendiente de crear). Usa un modelo placeholder que siempre falla la carga a propósito, para forzar y verificar el camino de fallback desde el primer día.

**Qué NO hacer en esta sesión**:
- No implementes CRDT/colaboración todavía (depende de que exista algo que colaborar).
- No implementes math handwriting, voz, ni avatar — todos dependen de que este motor base esté sólido primero.
- No recolectes dataset real de niños en esta sesión — eso requiere el protocolo de consentimiento (`dataset_collection.py`) que es su propia sesión con sus propios gates (G42-G44).

Al terminar: resumen de siempre, más una demo concreta (aunque sea manual): dibujar un cubo a mano, ver que se ofrecen 2-3 candidatos con confianza real, confirmar, y ver la figura 3D resultante — si esa demo no funciona de punta a punta, la sesión no está completa aunque las pruebas unitarias pasen.
