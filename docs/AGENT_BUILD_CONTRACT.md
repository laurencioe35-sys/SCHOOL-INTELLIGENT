# Contrato de construccion automatica

El loop no considera una tarea nueva como terminada porque exista su carpeta.
Una tarea que realmente deba producir codigo debe declarar en
`ai-agents-engine/config/erp_build_backlog.json`:

- `implementation_spec`: requisitos funcionales y no funcionales extraidos de la documentacion.
- `target_files`: lista exacta de archivos que el escritor puede modificar.
- `requires_code_generation: true`.
- `required_roles` con `code_writer`, `quality`, `security`, `review`, `repair` y `verify`.
- `validation_command` ejecutable y `execute_validation: true`.

El `GeminiCodeWriterAgent` solo escribe los archivos de `target_files`, rechaza
rutas fuera del workspace y falla si Gemini no esta configurado. El runner no
acepta una tarea de generacion sin este contrato.

## Estados validos

1. `MAINTAINING`: tarea existente verificada; no implica codigo nuevo.
2. `BUILDING`: hay tareas con especificacion ejecutable pendientes.
3. `BLOCKED`: falta contrato, dependencia, credencial, prueba o revision.
4. `COMPLETED`: Gemini escribio el cambio, las pruebas pasaron y security/review/verify dejaron evidencia persistida.

## Regla de porcentajes

El porcentaje de backlog no es el porcentaje de la plataforma. El porcentaje de
un area solo puede subir cuando sus tareas tienen evidencia ejecutable y todos
los gates documentados. Credenciales de proveedores, contratos regulatorios y
fuentes reales de audio no se sustituyen por mocks.
