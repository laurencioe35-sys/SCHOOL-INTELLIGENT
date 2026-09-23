/**
 * Sincronización de pizarra 3D con Yjs sobre WebSockets.
 *
 * Mejoras sobre la versión inicial (que solo aceptaba cualquier conexión
 * y perdía todo si el proceso se reiniciaba):
 *   1. AUTENTICACIÓN: exige un token válido emitido por core-erp-backend
 *      (mismo esquema HMAC, ver auth.ts) antes de aceptar la conexión.
 *      Sin eso, cualquiera que supiera el roomId podía conectarse y editar.
 *   2. PERSISTENCIA: el estado de cada aula se guarda a disco (snapshot
 *      binario de Yjs) cada vez que cambia y al desconectar el último
 *      cliente, y se recupera automáticamente si el servidor se reinicia
 *      a mitad de una clase.
 *   3. MULTI-INSTANCIA (nuevo, ver crdt_bus.ts): cada update local se
 *      retransmite también por Redis Pub/Sub, para que otras réplicas de
 *      este mismo servidor (detrás de un load balancer) mantengan sus
 *      copias del Y.Doc sincronizadas y alcancen a SUS propios clientes
 *      locales, sin lo cual escalar a 2+ instancias perdía mensajes
 *      entre alumnos conectados a réplicas distintas.
 */
import { WebSocketServer, WebSocket } from "ws";
import * as Y from "yjs";
import * as fs from "fs";
import * as path from "path";
import { verifyErpToken } from "./auth.js";
import { CrdtBus } from "./crdt_bus.js";

interface Room {
  doc: Y.Doc;
  clients: Set<WebSocket>;
  saveTimer: NodeJS.Timeout | null;
}

const rooms = new Map<string, Room>();
const STORAGE_DIR = process.env.CRDT_STORAGE_DIR ?? path.join(process.cwd(), "storage");
const bus = new CrdtBus();
const AUTHORIZATION_API_URL = (process.env.CRDT_AUTHORIZATION_API_URL ?? "").replace(/\/$/, "");
const AUTHORIZATION_SERVICE_KEY = process.env.CRDT_AUTHORIZATION_SERVICE_KEY ?? "";

if (!fs.existsSync(STORAGE_DIR)) {
  fs.mkdirSync(STORAGE_DIR, { recursive: true });
}

function storagePathFor(roomId: string): string {
  const safeId = roomId.replace(/[^a-zA-Z0-9_-]/g, "_");
  return path.join(STORAGE_DIR, `${safeId}.bin`);
}

function persistRoom(roomId: string, room: Room) {
  const snapshot = Y.encodeStateAsUpdate(room.doc);
  fs.writeFileSync(storagePathFor(roomId), snapshot);
}

function loadRoomFromDisk(roomId: string, doc: Y.Doc) {
  const filePath = storagePathFor(roomId);
  if (fs.existsSync(filePath)) {
    const data = fs.readFileSync(filePath);
    Y.applyUpdate(doc, new Uint8Array(data));
    console.log(`[crdt_sync] Estado del aula '${roomId}' recuperado desde disco (${data.length} bytes)`);
  }
}

async function getOrCreateRoom(roomId: string): Promise<Room> {
  let room = rooms.get(roomId);
  if (!room) {
    const doc = new Y.Doc();
    loadRoomFromDisk(roomId, doc);
    room = { doc, clients: new Set(), saveTimer: null };
    rooms.set(roomId, room);

    // Se suscribe UNA vez por sala (no por cliente): al recibir una
    // actualización que otra réplica ya aplicó a SU copia del Y.Doc, la
    // aplicamos aquí también y la reenviamos a nuestros propios clientes
    // locales — ellos nunca vieron ese mensaje porque llegó por WebSocket
    // a la otra instancia, no a esta.
    await bus.subscribeRoom(roomId, (update) => {
      Y.applyUpdate(room!.doc, update, "remote-bus");
      for (const client of room!.clients) {
        if (client.readyState === WebSocket.OPEN) {
          client.send(Buffer.from(update));
        }
      }
      scheduleSave(roomId, room!);
    });
  }
  return room;
}

function scheduleSave(roomId: string, room: Room) {
  if (room.saveTimer) clearTimeout(room.saveTimer);
  room.saveTimer = setTimeout(() => persistRoom(roomId, room), 1000);
}

async function authorizeClassroomConnection(userPayload: { sub: string; org: string }, roomId: string): Promise<boolean> {
  // Fail closed: a valid session alone is insufficient; the backend owns
  // the authoritative classroom-to-tenant relation.
  if (!AUTHORIZATION_API_URL || !AUTHORIZATION_SERVICE_KEY) return false;
  try {
    const response = await fetch(`${AUTHORIZATION_API_URL}/agents/internal/crdt-authorize`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CRDT-Service-Key": AUTHORIZATION_SERVICE_KEY },
      body: JSON.stringify({ user_id: userPayload.sub, organization_id: userPayload.org, classroom_id: roomId }),
      signal: AbortSignal.timeout(3000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function startCrdtServer(port: number) {
  await bus.connect();

  const wss = new WebSocketServer({
    port,
    verifyClient: (info, done) => {
      const url = new URL(info.req.url ?? "/", "http://localhost");
      const token = url.searchParams.get("token");

      if (!token) {
        done(false, 401, "Falta el parámetro token");
        return;
      }
      // verifyErpToken ahora es async (consulta Redis para revocación),
      // así que `done` se llama dentro del .then() en vez de sincrónicamente.
      verifyErpToken(token)
        .then((payload) => {
          if (!payload) {
            done(false, 401, "Token inválido, expirado o revocado");
            return;
          }
          (info.req as any).userPayload = payload;
          done(true);
        })
        .catch(() => done(false, 500, "Error verificando el token"));
    },
  });

  wss.on("connection", async (ws, req) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    const roomId = url.searchParams.get("room") ?? "default";
    const userPayload = (req as any).userPayload;

    if (!await authorizeClassroomConnection(userPayload, roomId)) {
      console.warn(`[crdt_sync] Rejected classroom authorization for ${userPayload.sub} in '${roomId}'`);
      ws.close(1008, "Unauthorized classroom");
      return;
    }

    const room = await getOrCreateRoom(roomId);
    room.clients.add(ws);
    console.log(`[crdt_sync] Usuario ${userPayload.sub} (${userPayload.role}) conectado a aula '${roomId}'`);

    const initialState = Y.encodeStateAsUpdate(room.doc);
    ws.send(initialState);

    ws.on("message", (data: Buffer) => {
      // The shared board is teacher-controlled. UI controls cannot prevent a
      // forged Yjs update sent directly from a student's browser.
      if (userPayload.role !== "teacher" && userPayload.role !== "admin") {
        console.warn(`[crdt_sync] Rejected board update from ${userPayload.sub} (${userPayload.role}) in '${roomId}'`);
        return;
      }
      Y.applyUpdate(room.doc, new Uint8Array(data));
      for (const client of room.clients) {
        if (client !== ws && client.readyState === WebSocket.OPEN) {
          client.send(data);
        }
      }
      // Reenvía a las demás réplicas (si las hay) para que sus propios
      // clientes locales también reciban este cambio.
      bus.publishUpdate(roomId, new Uint8Array(data)).catch((err) =>
        console.error(`[crdt_sync] Error publicando en el bus para '${roomId}':`, err)
      );
      scheduleSave(roomId, room);
    });

    ws.on("close", () => {
      room.clients.delete(ws);
      if (room.clients.size === 0) {
        persistRoom(roomId, room);
        if (room.saveTimer) clearTimeout(room.saveTimer);
        rooms.delete(roomId);
        bus.unsubscribeRoom(roomId).catch((err) =>
          console.error(`[crdt_sync] Error desuscribiendo '${roomId}' del bus:`, err)
        );
      }
    });
  });

  console.log(`[crdt_sync] Servidor CRDT escuchando en puerto ${port} (auth + persistencia + bus multi-instancia activados)`);
  return wss;
}
