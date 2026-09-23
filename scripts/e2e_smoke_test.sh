#!/usr/bin/env bash
# Test de humo END-TO-END real.
#
# A diferencia de los tests unitarios de cada módulo (pytest en el ERP,
# el pipeline de agentes solo, la suite de CRDT sola), este script prueba
# que los 4 módulos FUNCIONAN CONECTADOS: un profesor real se registra en
# el ERP, crea un aula real, el ai-agents-engine genera una sugerencia
# real, y esa sugerencia llega — vía el servidor CRDT real, con el token
# real emitido por el backend Python — a un alumno real matriculado.
#
# Requiere: Postgres y Redis corriendo, y las 3 variables de entorno de
# abajo consistentes entre sí (el mismo ERP_SECRET_KEY en ambos servicios).
#
# Uso: bash scripts/e2e_smoke_test.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHARED_SECRET="e2e-smoke-$(date +%s)"
TS=$(date +%s)

echo "=== Levantando core-erp-backend ==="
cd "$ROOT_DIR/core-erp-backend"
ERP_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/erp_educativo" \
ERP_REDIS_URL="redis://localhost:6379/0" \
ERP_SECRET_KEY="$SHARED_SECRET" \
CORS_ALLOWED_ORIGINS="http://localhost:5173" \
setsid nohup uvicorn main:app --host 127.0.0.1 --port 8200 > /tmp/e2e_backend.log 2>&1 < /dev/null &
BACKEND_PID=$!

echo "=== Levantando multimedia-stream-server (CRDT) ==="
cd "$ROOT_DIR/multimedia-stream-server"
ERP_SECRET_KEY="$SHARED_SECRET" setsid nohup npx tsx server.ts > /tmp/e2e_crdt.log 2>&1 < /dev/null &
CRDT_PID=$!

sleep 4

cleanup() {
  # PID-based kill no basta aquí: `setsid nohup npx tsx server.ts &` crea un
  # árbol de procesos (npx -> tsx -> node) y el PID capturado por bash es
  # solo el del proceso más externo — matarlo solo a él deja el resto vivo.
  # Se probó esto en carne propia: la primera versión de este script dejaba
  # procesos node huérfanos corriendo en el puerto 4444 tras cada corrida.
  pkill -f "uvicorn main:app" 2>/dev/null || true
  pkill -f "tsx server.ts" 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Registrando profesor y alumno reales ==="
TEACHER_TOKEN=$(curl -sf -X POST http://127.0.0.1:8200/auth/register -H "Content-Type: application/json" \
  -d "{\"full_name\":\"Prof Smoke\",\"email\":\"smoke_teacher_$TS@colegio.pe\",\"password\":\"clave123\",\"role\":\"teacher\",\"organization_name\":\"Colegio Smoke\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

STUDENT_TOKEN=$(curl -sf -X POST http://127.0.0.1:8200/auth/register -H "Content-Type: application/json" \
  -d "{\"full_name\":\"Alumno Smoke\",\"email\":\"smoke_student_$TS@colegio.pe\",\"password\":\"clave123\",\"organization_name\":\"Colegio Smoke\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

STUDENT_ID=$(python3 -c "
import base64, json
p = '$STUDENT_TOKEN'.split('.')[0]
p += '=' * (-len(p) % 4)
print(json.loads(base64.urlsafe_b64decode(p))['sub'])
")

echo "=== Creando aula real y matriculando al alumno ==="
CLASSROOM_ID=$(curl -sf -X POST http://127.0.0.1:8200/classrooms -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TEACHER_TOKEN" -d '{"name":"Aula Smoke Test"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -sf -X POST http://127.0.0.1:8200/students/enroll -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TEACHER_TOKEN" \
  -d "{\"student_id\":\"$STUDENT_ID\",\"classroom_id\":\"$CLASSROOM_ID\"}" > /dev/null

echo "=== Generando sugerencia real con ai-agents-engine ==="
cd "$ROOT_DIR/ai-agents-engine"
AI_PAYLOAD=$(python3 -c "
from main_agents import process_chunk
result = process_chunk('Hoy vamos a estudiar el triangulo equilatero', 'session-smoke')
import json
print(json.dumps(result.ui_component.payload))
")
echo "Payload de IA: $AI_PAYLOAD"

echo "=== Publicando en la pizarra CRDT real y verificando que el alumno lo recibe ==="
cd "$ROOT_DIR/multimedia-stream-server"

TMP_CHECK_SCRIPT=$(mktemp /tmp/e2e_check_XXXXXX.mjs)
cat > "$TMP_CHECK_SCRIPT" << 'NODESCRIPT'
import WebSocket from "ws";
import * as Y from "yjs";

const { TEACHER_TOKEN, STUDENT_TOKEN, CLASSROOM_ID, AI_PAYLOAD } = process.env;
const payload = JSON.parse(AI_PAYLOAD);

function connect(token) {
  return new Promise((resolve, reject) => {
    const doc = new Y.Doc();
    const ws = new WebSocket(`ws://localhost:4444?room=${CLASSROOM_ID}&token=${token}`);
    ws.on("unexpected-response", (_r, res) => reject(new Error("HTTP " + res.statusCode)));
    ws.on("error", reject);
    ws.on("message", (data) => Y.applyUpdate(doc, new Uint8Array(data)));
    doc.on("update", (u, origin) => {
      if (origin === "local" && ws.readyState === WebSocket.OPEN) ws.send(u);
    });
    ws.on("open", () => resolve({ doc, ws }));
  });
}

async function main() {
  const teacher = await connect(TEACHER_TOKEN);
  const student = await connect(STUDENT_TOKEN);
  await new Promise((r) => setTimeout(r, 300));

  teacher.doc.transact(() => {
    teacher.doc.getMap("pizarra").set("ai_suggestion", payload);
  }, "local");
  await new Promise((r) => setTimeout(r, 500));

  const seen = Object.fromEntries(student.doc.getMap("pizarra").entries());
  const ok = JSON.stringify(seen.ai_suggestion) === JSON.stringify(payload);

  console.log(ok ? "PASS" : "FAIL");
  teacher.ws.close();
  student.ws.close();
  process.exit(ok ? 0 : 1);
}

main().catch((err) => {
  console.error("ERROR:", err.message);
  process.exit(1);
});
NODESCRIPT

TEACHER_TOKEN="$TEACHER_TOKEN" STUDENT_TOKEN="$STUDENT_TOKEN" CLASSROOM_ID="$CLASSROOM_ID" AI_PAYLOAD="$AI_PAYLOAD" \
  node "$TMP_CHECK_SCRIPT"
rm -f "$TMP_CHECK_SCRIPT"

echo ""
echo "✅ E2E SMOKE TEST: ai-agents-engine -> core-erp-backend (auth real + classroom real) -> multimedia-stream-server -> alumno real"
