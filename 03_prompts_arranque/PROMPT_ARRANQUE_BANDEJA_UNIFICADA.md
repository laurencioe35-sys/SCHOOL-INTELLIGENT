# Prompt de arranque — Frontend: Bandeja Unificada de Mensajería (octavo módulo real del ERP)

> **Rige el Apéndice A de CLAUDE.md (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**: ningún componente de UI se fusiona con otro por compacidad. Corre el checklist de la sección 13 antes de cada commit — gate G47.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: este contenido ya vive como entrada estructurada en `agents/runtime/tasks/module_backlog.yaml` del ERP y el orquestador lo consume automáticamente (sección 56-57 del contrato). Pegar este prompt a mano sigue funcionando para una sesión suelta o de depuración puntual, pero ya no es el mecanismo principal — el flujo por defecto es "ejecuta el loop autónomo contra el backlog".

Mismo repositorio `erp-enterprise/`. Requiere que la sesión de Facebook/Instagram ya exista — el endpoint backend que devuelve mensajes mezclados de WhatsApp+Facebook+Instagram debe estar funcionando antes de construir esto.

---

## PROMPT

Lee `CLAUDE.md`, sección de design-system (`panels/SplitPanel.tsx`, `panels/DockablePanel.tsx`). Esta sesión es la primera puramente de frontend de la secuencia — hasta ahora todo fue backend. El criterio de éxito distinto aquí: la UI debe funcionar en los 3 estados de degradación ya definidos en el contrato (`ONLINE_FULL`/`DEGRADED_NO_AI`/`DEGRADED_LOCAL_ONLY` — el mismo patrón de `DegradedModeManager` de la Pizarra, adaptado aquí a "sin conexión al backend de mensajería" en vez de "sin red").

**Objetivo de esta sesión**: construir la bandeja unificada de mensajería como una feature de frontend separada (`frontend/src/features/unified-inbox/`), consumiendo el endpoint ya construido.

**Alcance de esta sesión, siguiendo la directiva de arquitectura (un componente = una responsabilidad)**:
1. `IMPLEMENT`: `UnifiedInboxPanel.tsx` — orquesta el layout (usa `SplitPanel`), pero NO contiene lógica de fetching ni de formato de mensaje — solo composición.
2. `IMPLEMENT`: `useUnifiedInboxMessages.ts` — hook que consume el endpoint (TanStack Query), responsable únicamente de estado de datos (loading/error/data), sin JSX.
3. `IMPLEMENT`: `MessageThreadList.tsx` — lista de conversaciones, responsabilidad única: renderizar la lista, no decide de qué proveedor viene cada mensaje.
4. `IMPLEMENT`: `ProviderBadge.tsx` — componente pequeño y separado solo para el ícono/color de WhatsApp vs. Facebook vs. Instagram — NO lo insertes como lógica condicional dentro de `MessageThreadList.tsx`, es exactamente el tipo de "responsabilidad accesoria absorbida por el componente principal" que la directiva prohíbe en la sección 2.2.
5. `IMPLEMENT`: `MessageComposer.tsx` — responsabilidad única: redactar y enviar, sin saber de la lista ni del estado de la bandeja completa.
6. `IMPLEMENT`: `unifiedInboxDegradedMode.ts` — máquina de estados separada (no mezclada dentro de un componente) para el caso "backend de mensajería no responde" → banner de aviso, nunca una pantalla en blanco o un crash.

**Qué NO hacer en esta sesión**:
- No metas `ProviderBadge`, `MessageComposer` y `MessageThreadList` en un solo archivo "para que sea más fácil de revisar" — es precisamente el patrón que el Apéndice A prohíbe en la sección 3 y 8.
- No implementes envío de mensajes nuevos a Instagram/Facebook todavía si el backend de esa sesión dejó esas rutas como stub — el frontend debe manejar ese `NotImplementedError` como un estado de UI explícito (botón deshabilitado con tooltip), no ocultarlo.
- No toques el backend en esta sesión.

Al terminar: mismo resumen de siempre, más confirmación explícita de que corriste el checklist de la sección 13 del Apéndice A sobre los 6 archivos nuevos y ninguno quedó consolidado innecesariamente.
