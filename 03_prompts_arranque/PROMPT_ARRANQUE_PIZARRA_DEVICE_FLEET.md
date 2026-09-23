# Prompt de arranque — Pizarra: Gestión de Flota de Paneles Físicos

> **Rige el Apéndice A**. Gate G47.

## Antes de pegar en Claude Code
> Vive como `device_fleet` en el backlog, gate G36. Sin dependencias.

## PROMPT
Lee `CLAUDE.md`, sección 22 (`ota_update_manager.py` — código de referencia completo) y sección 15/19 del ERP (patrón de identidad de dispositivo, certificado por panel).

**Objetivo**: rollout de firmware con fase canario obligatoria (5% primero) + rollback automático si el canario no reporta salud.

**Alcance**: `ota_update_manager.py` tal cual; `device_identity.py` reutilizando literalmente el diseño de `field_operations/device_identity.py` del ERP (V3), no un esquema nuevo.

**Qué NO hacer**: no despliegues a la flota completa sin la fase canario — ni siquiera "para ir más rápido" en un ambiente de prueba, porque el hábito importa más que la excepción puntual.

Al terminar: resumen de siempre + prueba de que un canario fallido detiene el rollout automáticamente, sin intervención manual para frenarlo.
