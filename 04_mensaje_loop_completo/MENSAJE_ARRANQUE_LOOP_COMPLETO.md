# Mensaje único de arranque del loop autónomo

## Requisito antes de pegarlo

- Repositorio `erp-enterprise/` creado, con `CLAUDE.md` (el ERP completo, V1–V18) en la raíz.
- `agents/runtime/tasks/module_backlog.yaml` presente con las 15 entradas (10 originales de V12 + 5 de colegio_virtual, V16).
- `docker compose up -d` corrido al menos una vez (PostgreSQL + Redis reales, no simulados — el loop va a fallar en STATIC_CHECK/INTEGRATION_TEST sin esto).
- Para las tareas `whiteboard_*` y `colegio_virtual_virtual_classroom`: repositorio `smart-whiteboard/` también existente, con su propio `CLAUDE.md`.

## El mensaje

```
Lee CLAUDE.md completo, incluyendo el Apéndice A (STRICT MODULAR CODE
ARCHITECTURE DIRECTIVE) y las Adendas V12–V18.

Ejecuta agents/runtime/orchestrator/loop_controller.py -> run_autonomous_loop()
contra agents/runtime/tasks/module_backlog.yaml, empezando con completed_ids
vacío (no se ha construido nada todavía).

Para cada tarea del backlog, en orden de dependencia:
1. Corre el pipeline completo DISCOVER -> SPECIFY -> PLAN -> [ARBITRATE] ->
   IMPLEMENT -> STATIC_CHECK -> UNIT_TEST -> INTEGRATION_TEST -> SECURITY ->
   REVIEW -> [CROSS-EXAMINATION] -> [ARBITRATE] -> REPAIR -> VERIFY ->
   CHECKPOINT -> COMMIT, sin saltarte pasos.
2. Aplica el checklist del Apéndice A §13 antes de cada commit (gate G47) --
   corre scripts/check_modular_architecture.py si ya existe, o el
   equivalente manual si todavía no lo has creado tú mismo en esta sesión.
3. Si el 'scope' o 'must_not' de una tarea en el backlog no es suficiente
   para decidir algo, busca el prompt PROMPT_ARRANQUE_*.md correspondiente
   -- tiene el detalle completo que el backlog resume.
4. Si encuentras una pregunta de negocio real sin resolver (no una decisión
   de diseño que tú puedas tomar), detente y pregúntame -- no la inventes.
5. Cuando termines una tarea, dame el resumen de siempre (gates que
   pasaron, archivos creados, preguntas abiertas) y sigue automáticamente
   con la siguiente tarea del backlog cuyas dependencias ya estén
   completas -- no esperes a que te lo pida de nuevo.
6. Cuando el backlog completo de 15 tareas esté agotado, pasa a modo
   MAINTAINING (Adenda V13, sección 65) -- no te declares "terminado".

Empieza ahora con la primera tarea disponible (accounting).
```

## Qué esperar realmente

Esto no corre solo de principio a fin sin supervisión — vas a interactuar en cada sesión cuando el loop se detenga por: una pregunta de negocio genuina (ej. el mecanismo de firma de webhook de Nequi/PSE que dejamos explícitamente sin inventar), un gate que falla y necesita tu revisión, o el límite práctico de una sesión de Claude Code (una tarea grande como Colegio Virtual completo probablemente no cabe en una sola sesión, aunque el mensaje esté pensado para encadenarlas).

La diferencia real frente a pegar 15 prompts es que **tú ya no decides el orden ni recuerdas las dependencias** — eso ya está en `module_backlog.yaml`. Tu trabajo pasa a ser: responder las preguntas reales cuando aparezcan, y revisar el resumen de cada tarea antes de dejar que siga con la siguiente.
