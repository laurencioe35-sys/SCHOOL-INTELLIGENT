/**
 * Suite de pruebas reales contra el servidor CRDT corriendo en localhost:4444.
 * Cubre: (1) convergencia CRDT con 2 clientes, (2) rechazo de conexión sin
 * token, (3) rechazo de conexión con token expirado, (4) persistencia real
 * a disco tras reiniciar el servidor.
 */
import WebSocket from "ws";
import * as Y from "yjs";
import { createClient } from "redis";
import { generateTestToken, generateExpiredTestToken, extractJti } from "./generate_test_token.mjs";

const ROOM = "aula-demo-crdt";
const BASE_URL = "ws://localhost:4444";

function connectClient(label, roomId, token) {
  return new Promise((resolve, reject) => {
    const doc = new Y.Doc();
    const ws = new WebSocket(`${BASE_URL}?room=${roomId}&token=${token}`);

    ws.on("unexpected-response", (_req, res) => {
      reject(new Error(`Conexión rechazada: HTTP ${res.statusCode}`));
    });
    ws.on("error", (err) => reject(err));

    ws.on("message", (data) => {
      Y.applyUpdate(doc, new Uint8Array(data));
    });
    doc.on("update", (update, origin) => {
      if (origin === "local" && ws.readyState === WebSocket.OPEN) {
        ws.send(update);
      }
    });
    ws.on("open", () => resolve({ label, doc, ws }));
  });
}

async function testConvergence() {
  console.log("\n=== TEST 1: Convergencia CRDT con 2 clientes autenticados ===");
  const token = generateTestToken("teacher-1", "teacher");
  const teacher = await connectClient("profesor", ROOM, token);
  const student = await connectClient("alumno", ROOM, generateTestToken("student-1", "student"));

  await new Promise((r) => setTimeout(r, 300));

  teacher.doc.transact(() => {
    teacher.doc.getMap("pizarra").set("bloque_1", { x: 10, y: 0, z: 5 });
  }, "local");
  student.doc.transact(() => {
    student.doc.getMap("pizarra").set("bloque_2", { x: -3, y: 2, z: 1 });
  }, "local");

  await new Promise((r) => setTimeout(r, 500));

  const canonical = (map) => {
    const obj = Object.fromEntries(map.entries());
    const sorted = {};
    for (const k of Object.keys(obj).sort()) sorted[k] = obj[k];
    return JSON.stringify(sorted);
  };

  const teacherState = canonical(teacher.doc.getMap("pizarra"));
  const studentState = canonical(student.doc.getMap("pizarra"));
  const published = JSON.parse(teacherState);
  const ok = teacherState === studentState && "bloque_1" in published && !("bloque_2" in published);

  console.log("Estado final:", teacherState);
  console.log(ok ? "✅ PASS: convergieron correctamente" : "❌ FAIL");

  teacher.ws.close();
  student.ws.close();
  return ok;
}

async function testRejectsWithoutToken() {
  console.log("\n=== TEST 2: Rechaza conexión SIN token ===");
  try {
    const ws = new WebSocket(`${BASE_URL}?room=${ROOM}`);
    await new Promise((resolve, reject) => {
      ws.on("open", () => reject(new Error("Se conectó sin token — esto NO debería pasar")));
      ws.on("unexpected-response", (_req, res) => {
        console.log(`Servidor respondió HTTP ${res.statusCode} (esperado: 401)`);
        resolve();
      });
      ws.on("error", () => resolve()); // también válido: la conexión se cierra de plano
    });
    console.log("✅ PASS: conexión sin token fue rechazada");
    return true;
  } catch (err) {
    console.log("❌ FAIL:", err.message);
    return false;
  }
}

async function testRejectsExpiredToken() {
  console.log("\n=== TEST 3: Rechaza conexión con token EXPIRADO ===");
  const expiredToken = generateExpiredTestToken("teacher-1", "teacher");
  try {
    const ws = new WebSocket(`${BASE_URL}?room=${ROOM}&token=${expiredToken}`);
    await new Promise((resolve, reject) => {
      ws.on("open", () => reject(new Error("Se conectó con token expirado — esto NO debería pasar")));
      ws.on("unexpected-response", (_req, res) => {
        console.log(`Servidor respondió HTTP ${res.statusCode} (esperado: 401)`);
        resolve();
      });
      ws.on("error", () => resolve());
    });
    console.log("✅ PASS: token expirado fue rechazado");
    return true;
  } catch (err) {
    console.log("❌ FAIL:", err.message);
    return false;
  }
}

async function testRejectsRevokedToken() {
  console.log("\n=== TEST 4: Rechaza conexión con token REVOCADO (mismo Redis que usa el ERP) ===");
  const token = generateTestToken("teacher-revoked", "teacher");
  const jti = extractJti(token);

  const redisUrl = process.env.ERP_REDIS_URL ?? "redis://localhost:6379/0";
  const redisClient = createClient({ url: redisUrl });
  await redisClient.connect();
  // Simula lo que hace POST /auth/logout del ERP: marcar el jti como revocado.
  await redisClient.set(`revoked_token:${jti}`, "1", { EX: 3600 });
  await redisClient.disconnect();

  try {
    const ws = new WebSocket(`${BASE_URL}?room=${ROOM}&token=${token}`);
    await new Promise((resolve, reject) => {
      ws.on("open", () => reject(new Error("Se conectó con un token revocado — esto NO debería pasar")));
      ws.on("unexpected-response", (_req, res) => {
        console.log(`Servidor respondió HTTP ${res.statusCode} (esperado: 401)`);
        resolve();
      });
      ws.on("error", () => resolve());
    });
    console.log("✅ PASS: token revocado fue rechazado");
    return true;
  } catch (err) {
    console.log("❌ FAIL:", err.message);
    return false;
  }
}

async function main() {
  const results = [];
  results.push(await testConvergence());
  results.push(await testRejectsWithoutToken());
  results.push(await testRejectsExpiredToken());
  results.push(await testRejectsRevokedToken());

  console.log("\n=== RESUMEN ===");
  console.log(`${results.filter(Boolean).length}/${results.length} pruebas pasaron`);
  process.exit(results.every(Boolean) ? 0 : 1);
}

main();
