# Prompt de arranque — Pizarra: Colaboración Multi-Usuario (CRDT)

> **Rige el Apéndice A (STRICT MODULAR CODE ARCHITECTURE DIRECTIVE)**. Gate G47.

## Antes de pegar en Claude Code
> Vive como `collaboration` en `agents/runtime/tasks/module_backlog.yaml` de este repo. Requiere `sketch_engine` completo.

## PROMPT
Lee `CLAUDE.md` (Pizarra), sección 7-8 (`useCollaborativeCanvas.ts`, `zone_conflict_bridge.py` — código de referencia completo) y `AUDITORIA_CONSISTENCIA_ERP_PIZARRA.md` (Hallazgo 2 — el import correcto es `app.platform.concurrency.resource_lock`, del ERP, NUNCA del tooling `agents/runtime/` de ningún repo).

**Objetivo**: CRDT (Yjs) para trazos simultáneos + locking de operaciones estructurales (conversión de zona).

**Alcance**: implementa ambos archivos tal cual el contrato; agrega IndexedDB offline-first (ya mencionado, sin código previo — complétalo); prueba de carga con 30 escritores simultáneos simulados (gate G33: p95 de sincronización < 150ms).

**Qué NO hacer**: no reimplementes el locking — impórtalo del paquete de plataforma del ERP como dependencia real, no copies el código.

Al terminar: resumen de siempre + métrica real de latencia p95 medida, no estimada.
