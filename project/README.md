# ERP Educativo Multimedia — Estado real del proyecto

Este documento es el mapa honesto de qué está **construido y probado de verdad**
en este entorno, y qué queda como **arquitectura correcta pero no ejecutada**
(porque requiere infraestructura que este sandbox no tiene: GPU, cámaras,
servidores WebRTC/K8s reales).

## ✅ Probado de punta a punta en este entorno

| Módulo | Qué se probó | Cómo verificarlo tú |
|---|---|---|
| `core-erp-backend` | Auth con revocación real de tokens, aulas, clases en vivo, Postgres+Alembic, Redis+batch worker, logging/métricas, multi-tenancy, matrícula, facturación, CORS, rate limiting por tenant/IP con protección de fuerza bruta en login, tracing distribuido con OpenTelemetry, resiliencia de conexión a Postgres + réplica de lectura real + backups automatizados, compliance de datos de menores, **tokens LiveKit reales firmados con `livekit-api`** (`POST /classrooms/{id}/start` y `/join-token`, JWT decodificado y verificado en tests), **pagos con Stripe real (SDK oficial)**, **`grading_agent` empujando calificaciones al ERP vía `/grades/submit-from-agent`**, **64/65 tests automatizados pasando** (1 skip honesto, ver nota abajo) | `docker compose up --build` y/o `cd core-erp-backend && pytest -v` |
| `immersive-frontend` | Compilación real verificada (`tsc --noEmit` + `vite build`), `StudentDashboard.tsx`, enrutamiento con `react-router-dom`, **roomId conectado al aula real** (ya no hardcodeado) | `cd immersive-frontend && npm install && npm run dev` |
| `ai-agents-engine` | Pipeline de 3 agentes con validación estricta de esquema Pydantic (uso puntual, ver `main_agents.py`) | `python main_agents.py` dentro de `ai-agents-engine/` |
| `ai-agents-engine/orchestrator` (**nuevo**) | Loop real de eventos (`while True` que consume una cola, no una función que hay que llamar a mano), blackboard compartido, registro de agentes plug-in, aislamiento de fallos por agente, **circuit breaker + dead-letter queue + cola con prioridad, con backend Redis compartido entre réplicas probado contra Redis real**, **proveedor LLM de respaldo con circuit breaker propio (primario→secundario→mock)**, **evals de calidad de agentes contra los agentes reales (14 casos dorados, gate de CI)**, **`grading_agent` sincronizando notas con el ERP real vía `erp_client.py`**, **53/53 tests automatizados pasando** | `cd ai-agents-engine && pytest -v` y `python3 evals/run_evals.py` |
| `ai-agents-engine/agents_v2/exercise_agent.py` (**nuevo**) | 10 agentes de materia (Matemática: Álgebra/Geometría/Trigonometría/Cálculo/Estadística, Física, Química, Biología, Anatomía, Inglés), ejercicios resueltos **originales**, **14/14 tests pasando** (uno por materia + aislamiento + corrección del ejercicio) | `cd ai-agents-engine && pytest tests/test_exercise_agents.py -v` |
| `multimedia-stream-server` (CRDT) | Servidor WebSocket + Yjs real, auth por token, **revocación de tokens sincronizada con el ERP vía Redis**, persistencia a disco, **bus multi-instancia por Redis Pub/Sub probado con 2 procesos de servidor reales e independientes convergiendo** | `npx tsx server.ts` y `node state/crdt_sync_test.mjs` (4/4) + `node state/crdt_multi_instance_test.mjs` (1/1) |
| **Los 4 módulos conectados** | `scripts/e2e_smoke_test.sh` — ERP real + IA real + CRDT real + tokens reales cruzando Python↔Node, corrido 2 veces de forma reproducible | `bash scripts/e2e_smoke_test.sh` |

### 🚦 Rate limiting por tenant/IP, con fuerza bruta bloqueada en login (nuevo)

Tercer bloqueante de la lista de robustez resuelto en esta sesión, sobre
`core-erp-backend`, probado contra Postgres + Redis reales (no mocks):

- **`observability/rate_limiter.py`** (nuevo): contador de ventana fija
  en Redis (`INCR`+`EXPIRE`). Se documenta a propósito su compromiso
  conocido (hasta ~2x el límite en el borde entre ventanas) en vez de
  presentarlo como perfecto — el objetivo es contener abuso, no facturar
  con precisión de milisegundo.
- **Fail-open deliberado**, y a propósito DISTINTO del fail-closed que
  ya usa la revocación de tokens en `api/auth.py`: si Redis no responde,
  el rate limiter deja pasar el tráfico en vez de tumbar el servicio
  completo. Revocación de tokens = decisión de seguridad (mejor
  rechazar de más). Rate limiting = decisión de disponibilidad (mejor
  que un tenant se quede sin límite unos segundos a que TODOS los
  tenants pierdan el servicio por un blip de Redis). Probado
  explícitamente rompiendo el cliente Redis a propósito
  (`test_rate_limiter_fails_open_when_redis_unavailable`).
- **Bucket por organización** (tenant) para tráfico autenticado — un
  colegio con un bug en su integración ya no puede saturar la cuota de
  los demás; probado con 2 organizaciones reales donde una se satura y
  la otra sigue con cuota completa.
- **Bucket `auth_ip` propio y más estricto** para `/auth/login` y
  `/auth/register` (comparten presupuesto a propósito: un atacante no
  puede evadir el límite de login alternando con registros falsos) —
  antes de esto no existía ningún freno a la fuerza bruta de contraseñas.
- Límites configurables por variable de entorno
  (`ERP_RATE_LIMIT_PER_ORG_PER_MIN`, `ERP_RATE_LIMIT_PER_IP_PER_MIN`,
  `ERP_RATE_LIMIT_AUTH_PER_IP_PER_MIN`, `ERP_RATE_LIMIT_WINDOW_SECONDS`),
  leídos en cada request (no una sola vez al importar el módulo) para
  que se puedan ajustar sin reiniciar el proceso de pruebas.
- Respuestas 429 incluyen `Retry-After` y headers `X-RateLimit-*`;
  `/metrics` y `/` quedan exentos para no romper el scraping de
  Prometheus ni el health check.
- **Se instaló Postgres real en este sandbox** (`apt-get install
  postgresql`) para poder correr toda la suite existente como línea
  base antes de tocar nada, y de nuevo después del cambio —
  `tests/test_rate_limit.py` (8/8) se suma a los 17 tests que ya
  existían, **25/25 en total**, todos contra infraestructura real.

**Bug preexistente encontrado al validar esto** (no introducido por este
cambio, no corregido — fuera de alcance de esta sesión): al re-correr
`scripts/e2e_smoke_test.sh` para confirmar que el rate limiting no
rompía la integración de los 4 módulos, el registro/login/matrícula/
generación de IA funcionaron correctamente, pero el paso final (verificar
que el alumno recibe la sugerencia por CRDT) falla con
`ERR_MODULE_NOT_FOUND: ws` — el script escribe su verificación en un
archivo temporal dentro de `/tmp` (`mktemp /tmp/e2e_check_XXXXXX.mjs`) y
Node resuelve módulos ESM según la ubicación del archivo, no del `cwd`
del `cd` previo, así que nunca encuentra `multimedia-stream-server/node_modules`.
Queda anotado como el siguiente bug a corregir en ese script (mover el
archivo temporal dentro de `multimedia-stream-server/` en vez de `/tmp`).

**Lo que esto NO resuelve todavía**: sigue siendo rate limiting de
ventana fija (no sliding window ni token bucket), no hay WAF ni
protección DDoS a nivel de red, y Postgres sigue siendo instancia única
sin réplica de lectura ni plan de backup — próximos en la lista.

### 🧠 Motor de agentes: de función única a loop real + agentes nuevos (nuevo)

Hasta la sesión anterior, `ai-agents-engine` no era realmente un motor: era
una función pura (`process_chunk`) que había que invocar a mano una vez por
fragmento — así la sigue usando `scripts/e2e_smoke_test.sh` (no se rompió
nada de lo que ya funcionaba). Eso probaba que el pipeline de 3 agentes era
correcto, pero no que el sistema pudiera **recibir** trabajo de forma
continua ni **crecer** en agentes sin tocar el núcleo. Se agregó
`ai-agents-engine/orchestrator/`:

- **`queue_adapter.py`**: cola de eventos real. En memoria por defecto
  (`asyncio.Queue`, probado); Redis Streams si defines `ERP_REDIS_URL`
  (mismo patrón de fallback honesto que `blackboard.js`/`queue.js` del
  proyecto de la pizarra — **no ejercitado en este sandbox**, no hay
  servidor Redis corriendo aquí).
- **`blackboard.py`**: estado compartido por sesión de clase entre
  agentes, para que se coordinen sin acoplarse (ej. el agente de quizzes
  lee el tema que detectó el pipeline base en el mismo ciclo, sin volver
  a detectarlo). Mismo patrón de fallback: memoria (probado) / Redis (no
  ejercitado aquí).
- **`registry.py`**: el "receptor de multiagentes" — cualquier clase que
  implemente `BaseAgent` se registra con `registry.register(...)` y el
  loop la invoca sola cuando el tipo de evento le interesa, **sin tocar
  `loop_engine.py`**. Aísla fallos: un agente que lanza una excepción no
  tumba el loop ni afecta a los demás agentes del mismo ciclo — probado
  explícitamente (`test_agent_failure_is_isolated_and_counted`).
- **`loop_engine.py`** (`AgentLoop`): el loop real. `run_forever()` corre
  un `while True` que consume eventos uno tras otro; `run_n()` es la
  variante determinista usada en los tests. Corre el pipeline base
  (context → pedagogical → ui_compiler) para fragmentos de transcripción
  y despacha el evento a todos los agentes registrados interesados,
  incluyendo el pipeline base como un ciclo más, no un caso especial.

**3 agentes nuevos**, registrados vía `agents_v2/` (ninguno existía antes):

- **`GradingAgent`**: califica respuestas de alumnos contra una rúbrica de
  puntos clave, con el mismo esquema estricto + LLM-real-o-mock que el
  resto del proyecto. Diseñado para **nunca inventar una nota alta**:
  marca `needs_teacher_review=true` ante cualquier ambigüedad.
- **`ContentGeneratorAgent`**: genera un mini-quiz de refuerzo a partir
  del tema que el pipeline base ya detectó — lee ese tema del blackboard
  en vez de volver a analizarlo, y explícitamente **no** genera preguntas
  de fragmentos de transición o de baja confianza (probado el caso
  negativo, no solo el feliz).
- **`AnalyticsAgent`**: no llama a ningún LLM — agrega en tiempo real lo
  que los demás agentes ya dejaron en el blackboard (temas cubiertos,
  acciones tomadas, calificaciones, errores) en un `AnalyticsSnapshot`
  con esquema propio.

**Bug real encontrado corriendo los tests** (no solo diseño en papel): el
mock de calificación comparaba el punto clave como substring exacto
(`"tres lados iguales" in respuesta`), lo que fallaba con respuestas
válidas donde las palabras no están contiguas en ese orden exacto
(`"sus tres lados... son iguales"`). Se corrigió a exigir que todas las
palabras del punto clave aparezcan en la respuesta, sin importar el orden.

**Regla que se mantuvo, actualizada**: el backend Redis del circuit
breaker y del dead-letter queue (ver sección de resiliencia abajo) **sí
corrió contra un Redis real** en esta sesión — se instaló `redis-server`
en este mismo sandbox específicamente para probar que el estado se
comparte entre réplicas, porque ese es justo el punto a demostrar y un
mock no lo puede probar. Lo que **sigue sin ejercitarse** es el backend
Redis de `queue_adapter.py` (Redis Streams) y de `blackboard.py`: ambos
están escritos y documentados, pero esta sesión no los puso a prueba —
mismo principio de no marcar "probado" lo que no se corrió. De hecho,
al intentar levantar `run_loop.py` con `ERP_REDIS_URL` configurado se
encontró una condición de carrera real en `RedisStreamEventQueue`
(el cursor `"$"` de `XREAD` puede perderse el primer mensaje si llega
antes de que el primer `consume()` empiece a escuchar) — quedó
identificado pero sin corregir, es el siguiente bug conocido a resolver
antes de dar por bueno ese backend específico.

### 🛡️ Capa de resiliencia: circuit breaker + dead-letter + prioridad, con estado compartido en Redis (nuevo)

Se identificaron 2 bloqueantes concretos para escalar el sistema a más de
un proceso/réplica, y se resolvieron ambos en esta sesión, probados
contra infraestructura real (no solo mocks):

**1. Estado del circuit breaker y del dead-letter queue, antes solo en
memoria de proceso.**

- `orchestrator/registry.py`: cada agente tiene su propio circuit
  breaker de 3 estados (`closed` → `open` tras N fallos seguidos → 
  `half_open` tras el cooldown, con recuperación automática). Antes de
  esta sesión, ese estado vivía en un `dict` de un solo proceso — con
  2+ réplicas de `ai-agents-engine`, un agente podía estar "abierto" en
  la réplica A y "cerrado" en la B al mismo tiempo. `RedisCircuitBreaker`
  (misma interfaz, backend distinto) centraliza ese estado en un hash de
  Redis compartido. Importante: usa `time.time()` como reloj por
  defecto (no `time.monotonic()`), porque el estado se lee y escribe
  desde procesos distintos y `monotonic()` no es comparable entre ellos.
- `orchestrator/dead_letter.py`: `RedisDeadLetterQueue` hace lo mismo
  para los eventos que rompen el pipeline base — antes se perdían al
  reiniciar el proceso o quedaban invisibles para otras réplicas; ahora
  viven en una lista de Redis que cualquier réplica (o un panel de
  soporte) puede leer y reintentar con `pop_for_retry()`.
- Ambos siguen el mismo patrón de fallback honesto que
  `blackboard.py`/`queue_adapter.py`: memoria de proceso si no hay
  `ERP_REDIS_URL`, Redis si lo hay — nadie que no tenga Redis configurado
  ve cambiar el comportamiento por defecto.
- **Se instaló Redis de verdad en este sandbox** (`apt-get install
  redis-server`) específicamente para probar esto — un mock no puede
  demostrar que 2 instancias independientes de `AgentRegistry` comparten
  circuito, hacía falta Redis real corriendo. `tests/test_resilience_redis.py`
  (5/5) construye deliberadamente 2 objetos separados apuntando al mismo
  Redis y prueba que uno ve el circuito que el otro abrió, sin
  compartir memoria entre sí. Se saltan explícitamente (no fingen pasar)
  si no hay Redis disponible en el entorno donde corran.
- `tests/test_resilience.py` (6/6, sin Redis) sigue cubriendo el
  comportamiento en memoria: apertura tras N fallos, recuperación
  half-open, aislamiento entre agentes, prioridad FIFO/urgente, y que
  una excepción del pipeline base ya no tumba `run_forever()` completo.

**2. `multimedia-stream-server` no podía correr en más de una instancia.**

- `state/crdt_bus.ts` (nuevo): cada actualización de la pizarra que un
  cliente aplica localmente se publica también en un canal de Redis
  Pub/Sub (`crdt:room:{roomId}`). Todas las réplicas están suscritas;
  al recibir una actualización que no se originó en sí mismas (se
  etiqueta con un `instanceId` único por proceso para evitar eco), la
  aplican a su copia del `Y.Doc` y la reenvían a sus propios clientes
  locales. Yjs garantiza que aplicar el mismo update en cualquier orden
  converge al mismo estado — no hay que resolver conflictos a mano.
- `state/crdt_sync.ts` se modificó para suscribirse al bus al crear una
  sala y publicar cada update entrante; fail-open deliberado si Redis
  cae a mitad de clase (seguir sirviendo localmente en vez de tumbar la
  sesión del salón conectado a esa réplica).
- **Probado con 2 procesos de servidor reales e independientes**
  (`state/crdt_multi_instance_test.mjs`): puertos distintos, carpetas de
  storage en disco distintas, cero memoria compartida entre ellos salvo
  Redis. Un cliente conectado a cada réplica edita la pizarra; ambos
  convergen al mismo estado. Si esto pasara sin el bus, sería porque los
  2 procesos comparten memoria — cosa que aquí es imposible por
  construcción, así que la convergencia solo puede venir de Redis
  Pub/Sub. La suite de un solo proceso (`crdt_sync_test.mjs`, 4/4) se
  re-corrió después del cambio para confirmar que no se rompió nada.

**Lo que esto NO resuelve todavía** (quedan en la lista de brechas de
robustez): el resto de `queue_adapter.py`/`blackboard.py` sigue sin
ejercitarse contra Redis real (ver arriba, incluye un bug de carrera
conocido en `RedisStreamEventQueue`); no hay rate limiting, tracing
distribuido, ni pruebas de carga; Postgres sigue siendo instancia única.

### 📚 Agentes de materia: ejercicios resueltos originales (nuevo)

Se pidió explícitamente incluir agentes de Matemática (todas las áreas),
Física, Química, Biología, Anatomía, Inglés, y "descargar los libros
Baldor" para generar ejercicios resueltos.

**Lo que NO se hizo, a propósito**: descargar o incluir libros con
copyright (Baldor u otros). Distribuir esos libros dentro del ERP sería
piratería, sin importar el fin educativo — no es un límite técnico, es
una decisión deliberada.

**Lo que sí se construyó** (`agents_v2/exercise_agent.py`): un agente de
materia parametrizable, con una instancia registrada por cada una de las
10 materias del catálogo (`SUBJECT_CATALOG`), que genera ejercicios
**resueltos paso a paso y originales** — nunca copiados de un libro:

- El prompt (`config/prompts.py::build_exercise_prompt`) instruye
  explícitamente a no repetir enunciados de libros conocidos y a redactar
  uno nuevo que enseñe el mismo concepto.
- El modo mock de prueba (sin `ANTHROPIC_API_KEY`) tampoco usa texto de
  ningún libro: son ejercicios de ejemplo escritos para este proyecto
  (`config/llm_client.py::_mock_exercise_response`), y se probó
  explícitamente que están **bien resueltos**, no solo bien formados
  (`test_math_algebra_exercise_is_actually_solved_correctly`).
- Aislamiento por materia probado: pedir un ejercicio de Física no
  dispara respuesta de los otros 9 agentes registrados para el mismo
  evento (`test_only_the_matching_subject_agent_responds`).
- Cobertura probada explícitamente contra el pedido original
  (`test_subject_catalog_covers_all_requested_areas`): las 5 áreas de
  matemática pedidas + física + química + biología + anatomía + inglés.

Si más adelante quieres contenido curricular real y con licencia legal en
vez del mock, los recursos abiertos (OER) usuales son
[OpenStax](https://openstax.org) (matemática, física, química, biología,
en inglés y algunos en español) y [Khan Academy](https://es.khanacademy.org)
— libres de usar, a diferencia de Baldor.

### 🏢 Multi-tenancy (organizaciones/colegios)

Cada `User` y `Classroom` pertenecen a una `Organization`. El registro
(`POST /auth/register`) ahora exige `organization_name` — si ya existe,
el usuario se une a ella; si no, se crea. Todas las queries de aulas
filtran por `organization_id` del usuario autenticado, y se probó
explícitamente que:
- Un profesor del Colegio A no ve las aulas del Colegio B en el listado.
- Un profesor del Colegio B que intenta operar sobre el UUID exacto de
  un aula del Colegio A recibe `404` (no `403`, para no confirmar
  siquiera que el aula existe).

**Migración con datos reales**: al agregar `organization_id` como columna
`NOT NULL`, la migración autogenerada por Alembic habría fallado contra
la base de desarrollo (que ya tenía usuarios y aulas de pruebas
anteriores). Se corrigió a mano con un patrón de 3 pasos (agregar
nullable → backfill a una organización "Legacy" → poner NOT NULL), que
es el patrón estándar para evolucionar esquemas en bases con datos vivos.

### 📊 Observabilidad

- **Logs estructurados en JSON** (`observability/logging_config.py`):
  cada evento de negocio (`user_registered`, `login_success`,
  `login_failed`, `grades_batch_consolidated`, `grade_moved_to_dead_letter`)
  se emite como una línea JSON con campos consistentes, lista para
  indexar en cualquier sistema de logs real.
- **Métricas Prometheus** (`observability/metrics.py`): el API expone
  `/metrics` con conteo y latencia de requests HTTP por endpoint; el
  batch worker expone las suyas en un puerto separado (`:9100/metrics`,
  configurable) porque corre en un proceso distinto al API.
- Probado con tráfico real: registro, login fallido, login exitoso, y
  se confirmó que tanto los logs como las métricas reflejan exactamente
  esos eventos.

### 🐛 Bug real encontrado y corregido durante la migración a Postgres

Al migrar de SQLite a Postgres, **una nota con un `student_id` inexistente
rompía todo el lote de consolidación** con `ForeignKeyViolation` — porque
SQLite, a diferencia de Postgres, no valida foreign keys por defecto y
dejaba pasar esos datos corruptos silenciosamente. Esto es exactamente el
tipo de bug que una migración a una base de datos real debe sacar a la
luz. La corrección: el batch worker ahora hace commit fila por fila y
manda los eventos inválidos a una cola `grades:dead_letter` en vez de
perder el lote completo o el evento corrupto. Hay un test de regresión
específico para esto.

### CI

`.github/workflows/ci-backend.yml` corre los tests automáticamente en
cada push/PR que toque `core-erp-backend/`, levantando Postgres y Redis
reales como servicios de GitHub Actions (no mocks).

### 🔗 Prueba end-to-end real: los 4 módulos conectados (nuevo)

Hasta la sesión anterior, cada módulo se había probado **por separado**:
el backend solo, el frontend solo (compilaba), el motor de IA solo, el
CRDT solo. Nunca se había probado la cadena completa. `scripts/e2e_smoke_test.sh`
corre eso de verdad:

1. Levanta `core-erp-backend` y `multimedia-stream-server` con el
   **mismo `ERP_SECRET_KEY`** (antes nunca se habían corrido juntos).
2. Registra un profesor y un alumno reales vía HTTP contra el backend real.
3. Crea un aula real y matricula al alumno (usando `students.py`, nuevo).
4. Corre `ai-agents-engine` de verdad sobre un texto de ejemplo.
5. El profesor publica esa sugerencia en la pizarra CRDT usando **su
   token real emitido por el backend Python**, validado por el servidor
   Node — la primera vez que se prueba esa validación cruzada entre
   lenguajes con un token real, no sintético.
6. Confirma que el alumno matriculado (con su propio token real) recibe
   exactamente esa sugerencia en su pizarra.

Se corrió 2 veces para confirmarlo reproducible. **Bug real encontrado y
corregido en el camino**: el cleanup del script mataba solo el PID más
externo del proceso backgroundeado (`setsid nohup npx tsx server.ts &`),
dejando el árbol de procesos hijo (`npx` → `tsx` → `node`) huérfano —
se corrigió a matar por patrón de proceso (`pkill -f`) en vez de por PID.

Este smoke test también corre en CI (`.github/workflows/ci-e2e.yml`).

### 🔒 Revocación de tokens (nuevo)

Antes, el esquema de tokens era puramente stateless: sin forma de
invalidar un token antes de que expirara (8h), aunque el usuario cerrara
sesión o fuera dado de baja. Se agregó:

- **`jti`** (ID único) en cada token nuevo.
- **`POST /auth/logout`**: guarda el `jti` en una lista de revocación en
  Redis, con TTL igual al tiempo restante de vida del token (así la
  lista se autolimpia sola).
- **El servidor CRDT (Node) también respeta la misma revocación**,
  consultando el mismo Redis — antes de esto, un token cerrado en el ERP
  seguía funcionando para conectarse a la pizarra. Diseñado *fail-closed*:
  si Redis no está disponible, se rechazan las conexiones nuevas en vez
  de aceptarlas sin poder verificar revocación.

Probado extremo a extremo: login → uso exitoso del token (ERP y CRDT) →
logout → el mismo token rechazado en **ambos** sistemas con `401`. También
se agregaron 3 tests unitarios (login/logout, logout doble, y que cerrar
una sesión no invalide otras sesiones activas del mismo usuario) y un 4to
test en la suite del CRDT que simula la revocación directamente contra
Redis. El frontend (`AuthContext.tsx`) también se actualizó: `logout()`
antes solo limpiaba el estado local sin avisar al backend.

### 🌐 CORS + roomId real (bugs reales corregidos, no solo "pulido")

- **CORS**: el backend no tenía `CORSMiddleware` configurado. Sin esto,
  el frontend (`localhost:5173`) no podía llamar al API (`localhost:8200`)
  — el navegador bloquea la petición antes de que llegue al servidor.
  Esto no se había detectado porque nunca se probó el frontend *contra*
  el backend en un navegador real, solo cada uno por separado.
- **roomId hardcodeado**: `ClassroomPage.tsx` usaba siempre `"aula-demo"`
  como sala de la pizarra CRDT, sin importar qué aula real crearas en el
  ERP — todas las aulas terminaban compartiendo el mismo estado. Se
  agregó `ClassroomListPage.tsx` (lista las aulas reales vía
  `GET /classrooms`) y se conectó el `classroom_id` real como parámetro
  de ruta (`/aula/:classroomId`).

### 🎓 Matrícula y facturación (nuevo)

- **`api/students.py`**: antes, un `student_id` arbitrario pasaba el
  filtro de `/grades/submit` sin verificar que el alumno estuviera
  matriculado en esa aula. Se agregó la tabla `Enrollment` y se endureció
  `/grades/submit` para exigir matrícula activa — probado con un test que
  confirma el rechazo (`test_grade_submit_requires_active_enrollment`).
- **`api/billing.py`**: pensiones/cobros con estado (`pending`, `paid`,
  `overdue`), aislados por organización. La pasarela de pago está
  simulada (mismo patrón que el LLM mock) porque una integración real
  (Culqi/Niubiz/MercadoPago) requiere una cuenta de comercio verificada
  con RUC que no existe en este entorno — el punto exacto de integración
  (`_charge_with_payment_gateway`) queda documentado.

### 🖥️ Frontend: rutas y panel del alumno (nuevo)

- **`StudentDashboard.tsx`**: vista de solo-lectura de la pizarra +
  perfil del alumno (notas, pensiones pendientes) — antes solo existía
  `TeacherDashboard.tsx`, así que cualquier alumno real habría visto la
  UI de control del profesor.
- **Enrutamiento formal con `react-router-dom`**: `/login` público,
  `/aula` protegida (`ProtectedRoute` redirige a `/login` si no hay
  sesión). El rol (profesor/alumno) se decide en `ClassroomPage` a
  partir del token, no de la URL — así un alumno no puede simplemente
  cambiar la ruta para ver el panel de profesor.
- **Esto sí se compiló de verdad en este entorno** (a diferencia de la
  primera versión, donde lo dejé sin instalar): `npm install` completo,
  `npx tsc --noEmit` sin errores, y `npx vite build` generando el bundle
  de producción.

### 🔑 Variables de entorno reales (con límite honesto)

`.env.example` documenta cada variable, y `scripts/generate_secrets.sh`
genera un `ERP_SECRET_KEY` real y fuerte para desarrollo. Lo que **no**
puedo generar por ti, porque son credenciales de cuentas de terceros que
no existen en este entorno: la API key de Anthropic (`ANTHROPIC_API_KEY`),
la de la pasarela de pago (`PAYMENT_GATEWAY_API_KEY`), y las de FaceIO
(`FACEIO_APP_ID`/`FACEIO_APP_SECRET`, documentadas por si retomas la idea
de negocio de compliance-as-a-service vista antes en esta conversación).
El `.env.example` explica dónde obtener cada una.

### 🔄 CI/CD completo (auditado y completado en esta sesión)

`.github/workflows/` no estaba presente en el zip que se subió para esta
sesión (se perdió al empaquetar, probablemente por exclusión de
directorios ocultos) aunque el README ya lo documentaba — se
reconstruyeron los 4 workflows exactamente como estaban descritos, más el
que faltaba de verdad:

- `ci-backend.yml`: pytest contra Postgres/Redis reales.
- `ci-agents.yml` (recreado — **no estaba documentado en ninguna versión
  anterior del README** pese a que `ai-agents-engine` ya tenía 53 tests
  propios, incluyendo `test_resilience_redis.py` contra Redis real, sin
  ningún workflow que los corriera): pytest + `evals/run_evals.py` como
  gate de calidad.
- `ci-frontend.yml`: `tsc --noEmit` + `vite build`.
- `ci-streaming.yml`: levanta el servidor CRDT real en el runner, corre
  la suite de convergencia/auth/persistencia y la suite multi-instancia.
- `ci-e2e.yml`: corre `scripts/e2e_smoke_test.sh` de punta a punta.
- `build-and-push-images.yml` (**nuevo, esto sí era lo único
  genuinamente faltante** — quedaba explícito en
  `deploy/k8s/README.md`): construye y sube a GHCR las 2 imágenes que
  referencian los manifiestos de Kubernetes. No ejecutado en este
  sandbox (no hay daemon de Docker disponible aquí); la sintaxis YAML de
  los 6 workflows se validó con `yaml.safe_load`.

**2 bugs reales encontrados y corregidos al auditar el estado del
proyecto antes de completar lo que faltaba** (no bugs introducidos en
esta sesión — ya estaban ahí, la integración de LiveKit/Stripe solo los
expuso al forzar una corrida completa de la suite):

1. **`X-Trace-Id` nunca aparecía en las respuestas**
   (`tests/test_tracing.py::test_response_includes_trace_id_header`
   fallaba incluso en aislamiento). Causa: `setup_tracing()` se llamaba
   ANTES de registrar CORS/rate-limit/metrics, lo que — por cómo
   Starlette construye su pila de middlewares en orden inverso al de
   registro — dejaba al middleware de OpenTelemetry como el MÁS INTERNO;
   su span se cerraba antes de que el control volviera a
   `metrics_middleware`, así que `current_trace_id()` siempre veía "sin
   span activo" ahí. Los spans SÍ se creaban y exportaban bien (por eso
   otros tests de tracing pasaban) — el bug era puntual al header.
   Corregido moviendo `setup_tracing()` al final del registro de
   middlewares, para que OpenTelemetry quede como la capa más externa.
   Ver el comentario largo en `core-erp-backend/main.py` con el detalle
   completo.
2. **`scripts/e2e_smoke_test.sh` fallaba con `ERR_MODULE_NOT_FOUND: ws`**
   al correrlo de verdad. Causa: el script generaba un `.mjs` temporal
   con `mktemp` en `/tmp` para verificar la sincronización CRDT, pero ese
   directorio no tiene acceso a los `node_modules` de
   `multimedia-stream-server` (donde SÍ están instalados `ws`/`yjs`).
   Corregido generando el temporal dentro de `multimedia-stream-server/`
   (con `.gitignore` agregado para no versionarlo). Verificado corriendo
   el script completo de punta a punta después del fix: `PASS`.

## ⚠️ Construido como arquitectura correcta, NO ejecutado aquí

| Módulo | Por qué no se ejecutó | Qué necesitas para probarlo tú |
|---|---|---|
| `streaming/webrtc_handler.ts` | Requiere un SFU real (LiveKit Cloud o self-hosted) | Cuenta de LiveKit + `livekit-server-sdk` |
| `streaming/ffmpeg_processor.ts` | Requiere el binario `ffmpeg` + una fuente de audio/video real | Instalar ffmpeg, conectar a un track real de LiveKit |
| `vision/gesture_tracking.ts` | Requiere cámara real + `@mediapipe/tasks-vision` corriendo en navegador | Correr en un navegador con webcam, no en este sandbox |
| Kubernetes / Media Pods por sesión | No hay clúster en este entorno | Ver sección "Roadmap de infraestructura" abajo |
| Integración del loop con el transcriptor Whisper real de `multimedia-stream-server` | `run_loop.py` usa un feed simulado (`_simulate_live_feed`), no audio real | Conectar el stream de transcripción real a `event_queue.publish(...)` en vez del feed simulado |
| Conexión real contra un servidor LiveKit (video/audio) | Los tokens se emiten y verifican de verdad (`tests/test_livekit_tokens.py`), pero conectarse a una sala real requiere un servidor LiveKit corriendo — infraestructura de media que este sandbox no tiene | Cuenta de LiveKit Cloud o el Helm chart oficial (ver `deploy/k8s/README.md`) |

**Nota sobre `ai-agents-engine/orchestrator` con Redis**: esta fila
existía en una versión anterior de este README porque en esa sesión el
sandbox no tenía Redis activo. En esta sesión y en la anterior SÍ lo
tiene, y `tests/test_resilience_redis.py` corre contra Redis real — se
sacó de la tabla de "no ejecutado" porque ya no es cierto.

**Regla que seguí:** ningún archivo del segundo grupo dice "probado" en su
código o en este README. Si el comentario dice "no ejecutado", es porque
no lo ejecuté — no es una forma de quedar bien, es literal.

---

## Cómo abrir esto en VS Code y seguir con Claude Code

1. Descomprime el zip y abre la carpeta `erp-educational-multimedia` completa en VS Code (`code erp-educational-multimedia`).
2. Instala **Claude Code** si no lo tienes (`npm install -g @anthropic-ai/claude-code` o la extensión de VS Code) y ábrelo desde la carpeta raíz del proyecto — así tiene contexto de los 4 módulos a la vez.
3. Copia `.env.example` a `.env` y complétalo (mínimo `ERP_SECRET_KEY`; deja `ANTHROPIC_API_KEY` vacío mientras uses el modo mock del motor de agentes).
4. Levanta el stack local:
   ```bash
   docker compose up --build
   ```
   Esto levanta Redis, el backend ERP, el batch worker, y el servidor CRDT — los 3 módulos que ya están probados.
5. Para el frontend (aparte, porque es lo único que falta instalar/compilar):
   ```bash
   cd immersive-frontend
   npm install
   npm run dev
   ```

### Con qué le pides ayuda a Claude Code primero (en orden de impacto real)
1. **Conectar el `ai-agents-engine` al `core-erp-backend`** — hoy son dos proyectos Python separados que solo se probaron juntos vía el script de smoke test, no vía un endpoint HTTP real del ERP.
2. **Reemplazar el mock del `llm_client.py`** por la llamada real a Claude, agregando tu `ANTHROPIC_API_KEY`.
3. **Rol de apoderado/padre de familia** — hoy solo existen student/teacher/admin; un padre necesita ver notas y pagar pensiones de su hijo sin ser "alumno".
4. **Módulo de asistencia** — tan básico como las notas en un ERP educativo real, y no existe todavía.
5. Recién después de esto: panel de administración de organización, notificaciones (email), WebRTC (LiveKit) y Kubernetes.

---

## ✅ Los 5 pendientes de la lista original, resueltos en esta sesión

Todo lo de esta sección se ejecutó y probó en este mismo sandbox contra
servicios reales (Postgres, Redis) — no son diseños en papel. Detalle
completo de qué se probó y qué NO en el docstring de cada módulo.

### 1. Tracing distribuido (`core-erp-backend/observability/tracing.py`)
OpenTelemetry real: FastAPI + SQLAlchemy + Redis instrumentados
automáticamente, `trace_id` correlacionado entre logs y spans, header
`X-Trace-Id` en cada respuesta. Probado con el exportador en memoria de
OpenTelemetry (`tests/test_tracing.py`, 4/4) — no un mock propio, el SDK
real generando spans reales. **No conectado todavía**: `ai-agents-engine`
y `multimedia-stream-server` no propagan `traceparent` entre sí (mismo
patrón, trabajo aparte).

### 2. Proveedor LLM de respaldo (`ai-agents-engine/config/llm_client.py`)
Primario (Anthropic) → respaldo (OpenAI o segunda cuenta de Anthropic) →
mock determinístico, con un circuit breaker por proveedor (abre tras N
fallos, cierra tras cooldown, medio-abierto para reintentar). Probado
inyectando fallos reales en el punto exacto de la llamada HTTP
(`tests/test_llm_client.py`, 7/7) — sin red real, mismo criterio que ya
usaba este archivo para el modo mock.

### 3. Evals de calidad de agentes (`ai-agents-engine/evals/`)
Dataset dorado de 14 casos que corre contra los agentes REALES (no
contra un doble), con checks de contenido específicos por agente —
incluye un check de seguridad que atrapa notas infladas ante respuestas
vacías. `python3 evals/run_evals.py` da un reporte legible y sale con
código 1 si el pass rate cae bajo el umbral (gate listo para CI).
`tests/test_evals.py` (4/4) incluye una prueba de que el harness SÍ
detecta una regresión inyectada, no solo que siempre dice "PASS".

### 4. Compliance de datos de menores (`core-erp-backend/api/privacy.py`)
Consentimiento parental con historial completo (no un booleano que se
sobreescribe), matrícula de un alumno menor BLOQUEADA sin consentimiento
activo (regla real, no decorativa), portabilidad de datos
(`GET /privacy/export/{id}`), derecho al olvido vía anonimización (las
notas/facturas se conservan por obligación de retención, pero sin PII
adjunta), y auditoría de cada acceso a datos de un menor. Migración de
Alembic autogenerada y aplicada (`cc1706fd3ce3`).
`tests/test_privacy.py` (10/10) contra Postgres real. Umbral de edad
configurable (`PRIVACY_MINOR_AGE_THRESHOLD`, default 14) — no es
asesoría legal, confirma el umbral aplicable con tu asesor legal.

### 5. Postgres como punto único de falla (`core-erp-backend/database/connection.py`)
Tres piezas, cada una probada contra Postgres real:
- **Resiliencia de conexión**: `pool_pre_ping` + retry con backoff
  exponencial al arrancar (`tests/test_db_resilience.py`).
- **Réplica de lectura real**: se montó una réplica en streaming
  replication de verdad en este sandbox (`scripts/setup_read_replica.sh`,
  puerto 5433) — base backup real con `pg_basebackup`, verificada con
  `pg_is_in_recovery()` y confirmando que rechaza escrituras. `get_db_read()`
  usa la réplica si está configurada y sana, y cae a la primaria
  automáticamente si no — probado con la réplica real y con una réplica
  simulada caída.
- **Backups automatizados con retención**: `scripts/backup_postgres.sh`
  (`pg_dump` formato custom + verificación de integridad +
  `find -mtime` para retención), probado de punta a punta —backup real,
  restore real en una base nueva, dato verificado — en
  `tests/test_backup_restore.py` (2/2).

**Límite honesto**: no hay failover automático de la PRIMARIA (si la
primaria se cae, las escrituras dejan de funcionar hasta promover
manualmente la réplica — eso requiere un orquestador como
Patroni/repmgr, fuera de alcance de esta sesión). Lo que se gana: las
lecturas sobreviven la caída de la réplica, y blips transitorios de red
ya no tumban conexiones del pool en silencio.

**Nota sobre el 1 test que queda en skip**: `test_db_resilience.py::test_get_db_read_uses_configured_replica_when_available`
se salta si la réplica de streaming del punto 5.2 no está corriendo en
ese momento del sandbox (el proceso manual en el puerto 5433 no
sobrevive un reinicio del servicio `postgresql` gestionado por systemd/
`service`, que solo controla el cluster principal) — correr
`scripts/setup_read_replica.sh` antes de la suite lo deja en verde.

---



| Fase | Qué se agrega | Cuándo tiene sentido |
|---|---|---|
| Ahora (`docker-compose.yml`) | Todo en una máquina, para desarrollo/demo | Hasta el primer piloto real con un colegio |
| LiveKit Cloud | Video/audio real sin operar tu propio SFU | Cuando tengas clases en vivo reales, no antes |
| Kubernetes + Media Pods | Aislar cada clase en vivo en su propio contenedor | Cuando tengas múltiples clases simultáneas y necesites que una no tumbe a las demás |
| MinIO/S3 + CDN | Servir modelos `.glb` y assets pesados rápido | Cuando el catálogo de contenido 3D crezca más allá de unos pocos assets |
