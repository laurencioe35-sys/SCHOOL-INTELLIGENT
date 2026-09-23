# Reglas globales de agentes

1. No inventar requisitos.
2. No modificar contratos sin actualizar pruebas y documentación.
3. No declarar PASS sin evidencia ejecutable.
4. Toda operación destructiva requiere autorización explícita.
5. Toda operación multi-tenant debe validar tenant_id en backend.
6. Los agentes trabajan por estados: DISCOVER -> PLAN -> IMPLEMENT -> TEST -> REVIEW -> REPAIR -> VERIFY.
7. Un fallo debe producir una tarea de reparación y conservar trazabilidad.
