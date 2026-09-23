# Instrucciones para Claude Code

Construir por incrementos verificables. Antes de editar:
- inspeccionar arquitectura;
- identificar contratos afectados;
- localizar pruebas existentes;
- evaluar impacto de seguridad y tenancy.

Después de editar:
- lint;
- type check;
- unit/integration tests;
- revisión de seguridad;
- actualizar documentación.

No usar stubs, TODOs vacíos ni funciones que aparenten implementar una capacidad que no implementan.
