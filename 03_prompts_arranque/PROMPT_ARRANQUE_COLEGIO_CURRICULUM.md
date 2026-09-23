# Prompt de arranque — Colegio Virtual: Currículo

> **Rige el Apéndice A de CLAUDE.md**: ningún archivo se fusiona por compacidad. Gate G47 antes de cada commit.

## Antes de pegar esto en Claude Code

> **Nota (post V12)**: vive como `colegio_virtual_curriculum` en `module_backlog.yaml`. Pegar a mano es válido para depuración puntual.

Mismo repositorio. Requiere `colegio_virtual_admissions` completo — un curso necesita poder asociarse a estudiantes ya matriculados.

---

## PROMPT

Lee `CLAUDE.md`, Adenda V15 (§73, árbol de `curriculum/`) y V18 (`syllabus_builder.py`, ya con código de referencia completo — impléméntalo tal cual).

**Objetivo**: `grade_levels.py`, `subjects.py`, `curriculum_standards.py`, `course_catalog.py`, `syllabus_builder.py`.

**Decisión ya resuelta, no la preguntes de nuevo**: normativa MEN Colombia (V17 §88) como base de `curriculum_standards.py` — pero recuerda que la V15 fue explícita en que la normativa exacta por país es una decisión de negocio; implementa `curriculum_standards.py` como catálogo **configurable**, no hardcodees los estándares reales de memoria — si no tienes la fuente oficial verificada, deja el catálogo vacío con la estructura correcta y una entrada de ejemplo marcada `is_placeholder=True`.

**Alcance**:
1. `curriculum_standards.py`: modelo de datos del estándar (código, descripción, área, grado) — sin contenido real inventado.
2. `grade_levels.py`/`subjects.py`: catálogo base, configurable por colegio.
3. `course_catalog.py`: cursos por periodo académico, referenciando `grade_levels`/`subjects`.
4. `syllabus_builder.py`: código ya dado en V18 — `validate_standard_references()` debe fallar si el estándar no existe en el catálogo cargado, incluidos los placeholders (un placeholder no es un estándar válido para publicar un sílabo real, solo para desarrollo).
5. `QA`: la prueba de V18 (`test_rejects_prerequisite_scheduled_after_dependent_topic`) debe pasar tal cual, más un caso nuevo: sílabo que referencia un estándar `is_placeholder=True` en un colegio marcado como "producción" → debe rechazarse (gate nuevo de esta sesión, documéntalo como `G56` si no existe ya).

**Qué NO hacer**: no implementes `gradebook/` (depende de que `course_catalog.py` exista primero, es la siguiente sesión) ni inventes contenido curricular real de ningún país sin fuente verificada.

Al terminar: resumen de siempre + confirmación de que `curriculum_standards.py` no tiene ningún estándar real inventado, solo estructura y placeholders explícitos.
