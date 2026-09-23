# Prompt de arranque — Colegio Virtual: Biblioteca de Contenido (content_library/)

> **Rige el Apéndice A de CLAUDE.md**: ningún archivo se fusiona por compacidad. Gate G47 antes de cada commit.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: vive como `colegio_virtual_content_library` en `module_backlog.yaml`, gate G61.

Mismo repositorio. Requiere `colegio_virtual_curriculum` — un material se asocia a un tema de sílabo existente.

---

## PROMPT

Lee `CLAUDE.md`, Adenda V21 completa (`licensing_compliance.py`, `content_versioning.py`, código+pruebas completos, y el agente **Content-Licensing**, `.claude/agents/content-licensing.md`).

**Objetivo**: implementar los 2 archivos ya dados, más `material_repository.py` (el único sin código de referencia previo — CRUD de materiales, sin decidir licencia, esa decisión vive exclusivamente en `licensing_compliance.py`).

**Alcance**:
1. `IMPLEMENT`: `material_repository.py` — almacenamiento de materiales (documento, video, enlace externo). Por defecto, todo material nuevo entra con `licensing_status='pending_review'` — nunca `'approved'` por defecto, ni siquiera para contenido subido por un coordinador académico.
2. `IMPLEMENT`: `licensing_compliance.py` tal cual (V21) — el agente Content-Licensing es el único que puede invocar `evaluate_licensing()` con un resultado que cambie el estado a `approved`.
3. `IMPLEMENT`: `content_versioning.py` tal cual (V21) — verifica con prueba real que `publish_new_version()` rechaza si `licensing_status != "approved"`, incluso si quien llama pasó el parámetro manualmente con un valor incorrecto (defensa en profundidad, no confía en que el llamador ya validó).
4. `SECURITY`: gate **G61** — prueba de que ningún material queda `approved` con el mismo rol en `uploaded_by_role` que lo subió originalmente (la prueba de referencia `test_teacher_cannot_self_approve_own_material` ya está en V21, complétala con fixtures reales).
5. `QA`: prueba de que un material asignado a un tema de sílabo en la semana 3 no cambia su contenido cuando se publica una versión nueva en la semana 8 — el estudiante que ya lo vio en la semana 3 sigue viendo la versión que usó, el sílabo debe referenciar la versión específica, no "la última disponible" de forma implícita.

**Qué NO hacer**: no implementes un flujo de "aprobación automática" para contenido de fuentes que "parecen confiables" (ej. Wikipedia, YouTube educativo) — toda licencia pasa por evaluación explícita, sin atajos por origen percibido como confiable.

Al terminar: resumen de siempre + confirmación de que un material con licencia `UNKNOWN` nunca llegó a estado `approved` en ninguna prueba, ni por el camino feliz ni por ningún caso borde que hayas probado.
