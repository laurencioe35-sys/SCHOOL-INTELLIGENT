/**
 * Prueba de INTEGRACIÓN MULTI-INSTANCIA — NUEVA, no existía en el
 * proyecto. Es el test que de verdad demuestra que se resolvió el
 * bloqueante #2 ("multimedia-stream-server no puede correr en más de
 * una instancia").
 *
 * A diferencia de crdt_sync_test.mjs (que prueba convergencia CRDT con
 * 2 clientes contra UN mismo proceso servidor — eso ya funcionaba antes
 * del bus, porque ambos clientes comparten el mismo `rooms` Map en
 * memoria), esta prueba levanta DOS PROCESOS de servidor real,
 * completamente independientes (distinto puerto, distinta carpeta de
 * storage en disco, cero memoria compartida entre ellos salvo Redis), y
 * conecta un cliente distinto a cada uno. Si el maestro (conectado a la
 * réplica A) edita la pizarra y el alumno (conectado a la réplica B) ve
 * ese cambio, la sincronización solo pudo haber viajado por Redis
 * Pub/Sub — es imposible que sea memoria compartida entre procesos de
 * Node distintos.
 *
 * Corre con: node state/crdt_multi_instance_test.mjs
 * (requiere Redis real en ERP_REDIS_URL — sin Redis, este test no
 * puede probar nada real y se debe saltar explícitamente, no fingir).
 */
import { spawn } from "child_process";
import { fileURLToPath } from "url";
import path from "path";
import fs from "fs";
import net from "net";
import WebSocket from "ws";
import * as Y from "yjs";
import { generateTestToken } from "./generate_test_token.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, "..");
const ROOM = "aula-multi-instancia";
const REDIS_URL = process.env.ERP_REDIS_URL ?? "redis://localhost:6379/0";
const SECRET = process.env.ERP_SECRET_KEY ?? "test-secret-key";

const PORT_A = 4501;
const PORT_B = 4502;
const STORAGE_A = path.join("/tmp", `crdt_storage_multi_a_${Date.now()}`);
const STORAGE_B = path.join("/tmp", `crdt_storage_multi_b_${Date.now()}`);

function waitForPort(port, timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tryConnect = () => {
      const sock = new net.Socket();
      sock.once("connect", () => {
        sock.destroy();
        resolve();
      });
      sock.once("error", () => {
        sock.destroy();
        if (Date.now() - start > timeoutMs) reject(new Error(`Timeout esperando puerto ${port}`));
        else setTimeout(tryConnect, 200);
      });
      sock.connect(port, "127.0.0.1");
    };
    tryConnect();
  });
}

function spawnServer(port, storageDir) {
  fs.mkdirSync(storageDir, { recursive: true });
  const child = spawn("npx", ["tsx", "server.ts"], {
    cwd: ROOT,
    env: {
      ...process.env,
      ERP_SECRET_KEY: SECRET,
      ERP_REDIS_URL: REDIS_URL,
      CRDT_PORT: String(port),
      CRDT_STORAGE_DIR: storageDir,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  child.stdout.on("data", (d) => (output += d.toString()));
  child.stderr.on("data", (d) => (output += d.toString()));
  child.getOutput = () => output;
  return child;
}

function connectClient(port, roomId, token) {
  return new Promise((resolve, reject) => {
    const doc = new Y.Doc();
    const ws = new WebSocket(`ws://localhost:${port}?room=${roomId}&token=${token}`);
    ws.on("unexpected-response", (_req, res) => reject(new Error(`HTTP ${res.statusCode}`)));
    ws.on("error", reject);
    ws.on("message", (data) => Y.applyUpdate(doc, new Uint8Array(data)));
    doc.on("update", (update, origin) => {
      if (origin === "local" && ws.readyState === WebSocket.OPEN) ws.send(update);
    });
    ws.on("open", () => resolve({ doc, ws }));
  });
}

async function main() {
  console.log("=== TEST: sincronización cruzada entre 2 procesos de servidor independientes ===");
  console.log(`Réplica A: puerto ${PORT_A} (storage: ${STORAGE_A})`);
  console.log(`Réplica B: puerto ${PORT_B} (storage: ${STORAGE_B})`);
  console.log(`Ambas apuntan al mismo Redis: ${REDIS_URL}`);

  const serverA = spawnServer(PORT_A, STORAGE_A);
  const serverB = spawnServer(PORT_B, STORAGE_B);

  let ok = false;
  try {
    await waitForPort(PORT_A);
    await waitForPort(PORT_B);
    await new Promise((r) => setTimeout(r, 300)); // margen para que ambos bus se conecten a Redis

    const teacherOnA = await connectClient(PORT_A, ROOM, generateTestToken("teacher-multi", "teacher"));
    const studentOnB = await connectClient(PORT_B, ROOM, generateTestToken("student-multi", "student"));

    await new Promise((r) => setTimeout(r, 300));

    // El maestro edita en la RÉPLICA A.
    teacherOnA.doc.transact(() => {
      teacherOnA.doc.getMap("pizarra").set("desde_replica_A", { texto: "hola desde A" });
    }, "local");

    // El alumno edita en la RÉPLICA B, al mismo tiempo.
    studentOnB.doc.transact(() => {
      studentOnB.doc.getMap("pizarra").set("desde_replica_B", { texto: "hola desde B" });
    }, "local");

    // Tiempo para que Redis Pub/Sub propague ambos cambios entre las 2 réplicas.
    await new Promise((r) => setTimeout(r, 600));

    const canonical = (map) => {
      const obj = Object.fromEntries(map.entries());
      const sorted = {};
      for (const k of Object.keys(obj).sort()) sorted[k] = obj[k];
      return JSON.stringify(sorted);
    };

    const stateOnA = canonical(teacherOnA.doc.getMap("pizarra"));
    const stateOnB = canonical(studentOnB.doc.getMap("pizarra"));

    console.log("Estado visto por el maestro (réplica A):", stateOnA);
    console.log("Estado visto por el alumno  (réplica B):", stateOnB);

    const bothKeysPresent = stateOnA.includes("desde_replica_A") && stateOnA.includes("desde_replica_B");
    ok = stateOnA === stateOnB && bothKeysPresent;

    console.log(
      ok
        ? "✅ PASS: el cambio de la réplica B llegó a la réplica A (y viceversa) SOLO por Redis Pub/Sub — no comparten memoria de proceso."
        : "❌ FAIL: las réplicas no convergieron — revisar logs de los servidores abajo."
    );

    if (!ok) {
      console.log("\n--- log réplica A ---\n" + serverA.getOutput());
      console.log("\n--- log réplica B ---\n" + serverB.getOutput());
    }

    teacherOnA.ws.close();
    studentOnB.ws.close();
  } catch (err) {
    console.log("❌ FAIL:", err.message);
    console.log("\n--- log réplica A ---\n" + serverA.getOutput());
    console.log("\n--- log réplica B ---\n" + serverB.getOutput());
  } finally {
    serverA.kill("SIGKILL");
    serverB.kill("SIGKILL");
    fs.rmSync(STORAGE_A, { recursive: true, force: true });
    fs.rmSync(STORAGE_B, { recursive: true, force: true });
  }

  console.log("\n=== RESUMEN ===");
  console.log(ok ? "1/1 prueba pasó" : "0/1 pruebas pasaron");
  process.exit(ok ? 0 : 1);
}

main();
