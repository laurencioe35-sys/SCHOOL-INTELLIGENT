# Prompt de arranque — Pizarra: Beamforming del Array de Micrófonos (Firmware)

> **Rige el Apéndice A**. Gate G47.

## Antes de pegar en Claude Code
> Vive como `audio_beamforming` en `agents/runtime/tasks/module_backlog.yaml`. Sin dependencias de otras tareas del backlog, pero SÍ depende de tener acceso al hardware real del array de micrófonos (§15) — no se valida solo con simulación.

## PROMPT
Lee `CLAUDE.md`, sección 28 (`beamformer.py` — algoritmo delay-and-sum, código de referencia completo) y sección 15 (especificación de hardware del array de 6-8 micrófonos MEMS).

**Objetivo**: implementar y VALIDAR `estimate_direction_of_arrival()` y `apply_beamforming()` contra el hardware real, no solo contra señales sintéticas generadas en Python.

**Decisión ya tomada, no la reabras**: delay-and-sum, no MVDR ni otro beamforming adaptativo — la justificación (presupuesto de cómputo del firmware del panel) ya está en §28. Si te parece que un método más sofisticado daría mejor resultado, documéntalo como mejora futura, no lo implementes en esta sesión sin que se decida explícitamente cambiar el presupuesto de hardware.

**Alcance**:
1. `IMPLEMENT`: el algoritmo tal cual, corriendo en el firmware (edge), no en el backend.
2. `QA`: prueba con grabación real de un array de micrófonos (o al menos una simulación acústica con eco de aula real, no solo señales limpias) — confirma que el AEC (cancelación de eco acústico, mencionado en §15) es necesario y evalúa si ya está cubierto o si esta sesión debe implementarlo también.
3. Mide la señal resultante (SNR) contra el motor STT del `voice_assistant` del ERP — el objetivo final es que el texto transcrito sea utilizable, no solo que el algoritmo "corra sin errores".

**Qué NO hacer**: no optimices el algoritmo más allá de lo que el hardware real puede sostener — un algoritmo más preciso que satura la CPU del panel es peor que uno más simple que sí corre en tiempo real.

Al terminar: resumen de siempre + métrica real de SNR/precisión de transcripción con el beamforming activo vs. un solo micrófono, no una afirmación sin número.
