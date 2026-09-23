/**
 * Bus de mensajería entre instancias del servidor CRDT — NUEVO.
 *
 * PROBLEMA QUE RESUELVE: `crdt_sync.ts` guarda `rooms` en un `Map` en
 * memoria de UN SOLO proceso. Con una sola instancia esto basta: todos
 * los clientes de una sala terminan en el mismo Map y `room.clients` los
 * alcanza a todos. Pero en cuanto pones 2+ réplicas de
 * `multimedia-stream-server` detrás de un load balancer (necesario para
 * escalar streaming en vivo a más de un salón concurrente), un alumno
 * conectado a la réplica B nunca ve las actualizaciones que el maestro
 * mandó a la réplica A — cada proceso tiene su propio Map aislado. Este
 * era el bloqueante #2 identificado en la revisión de robustez.
 *
 * SOLUCIÓN: cada actualización que un cliente local aplica se PUBLICA
 * también en un canal de Redis Pub/Sub (`crdt:room:{roomId}`); todas las
 * réplicas están suscritas a ese canal y, al recibir una actualización
 * que no se originó en sí mismas (se etiqueta con un `instanceId` único
 * por proceso para evitar eco infinito), la aplican a su copia local del
 * `Y.Doc` y la retransmiten a SUS clientes locales. El estado de cada
 * réplica converge al mismo documento por las garantías CRDT de Yjs:
 * aplicar el mismo update dos veces, o en cualquier orden, es
 * idempotente — no hay que resolver conflictos a mano.
 *
 * Mismo cliente `redis` v4 y misma variable ERP_REDIS_URL que ya usa
 * `auth.ts` para revocación de tokens: este proyecto YA trata a Redis
 * como infraestructura obligatoria en el servidor Node (falla en
 * cerrado si no está disponible para auth), así que el bus sigue esa
 * misma convención en vez de inventar un modo "sin Redis" que el resto
 * de este servidor no tiene. La única concesión es en `publishUpdate`:
 * si Redis se cae A MITAD de una clase ya en curso, se prefiere seguir
 * sirviendo la pizarra local (aunque las réplicas se desincronicen
 * temporalmente) antes que tumbar la sesión del salón que sí sigue
 * conectado a esta réplica.
 */
import { randomUUID } from "crypto";
import { createClient, type RedisClientType } from "redis";

const REDIS_URL = process.env.ERP_REDIS_URL ?? "redis://localhost:6379/0";

// Único por proceso: así cada réplica reconoce y descarta su propio eco
// cuando Redis le reenvía un mensaje que ella misma publicó.
export const INSTANCE_ID = randomUUID();

interface BusEnvelope {
  instanceId: string;
  updateB64: string;
}

export type RemoteUpdateHandler = (update: Uint8Array) => void;

export class CrdtBus {
  private publisher: RedisClientType;
  private subscriber: RedisClientType;
  private ready = false;
  private handlers = new Map<string, RemoteUpdateHandler>();

  constructor(redisUrl: string = REDIS_URL) {
    // node-redis v4 exige un cliente DEDICADO para modo subscriber (no
    // puede mezclar comandos normales con SUBSCRIBE en la misma
    // conexión) — de ahí el .duplicate().
    this.publisher = createClient({ url: redisUrl });
    this.subscriber = this.publisher.duplicate();
    this.publisher.on("error", (err) => console.error("[crdt_bus] Error en publisher:", err.message));
    this.subscriber.on("error", (err) => console.error("[crdt_bus] Error en subscriber:", err.message));
  }

  async connect(): Promise<void> {
    if (this.ready) return;
    await Promise.all([this.publisher.connect(), this.subscriber.connect()]);
    this.ready = true;
    console.log(`[crdt_bus] Conectado a Redis (${REDIS_URL}) — instancia ${INSTANCE_ID}`);
  }

  private channelFor(roomId: string): string {
    return `crdt:room:${roomId}`;
  }

  /** Publica una actualización aplicada localmente para que las demás
   * réplicas la reciban. Fail-open deliberado: si Redis no está listo,
   * NO lanza — la réplica local sigue funcionando para sus propios
   * clientes, solo pierde sincronía cross-réplica hasta reconectar. */
  async publishUpdate(roomId: string, update: Uint8Array): Promise<void> {
    if (!this.ready) return;
    const envelope: BusEnvelope = {
      instanceId: INSTANCE_ID,
      updateB64: Buffer.from(update).toString("base64"),
    };
    try {
      await this.publisher.publish(this.channelFor(roomId), JSON.stringify(envelope));
    } catch (err: any) {
      console.error(`[crdt_bus] No se pudo publicar en '${roomId}':`, err.message);
    }
  }

  /** Se suscribe al canal de una sala. Idempotente: si ya hay un
   * handler para esa sala (otro cliente local se unió a la misma),
   * no vuelve a suscribirse dos veces. */
  async subscribeRoom(roomId: string, onRemoteUpdate: RemoteUpdateHandler): Promise<void> {
    const channel = this.channelFor(roomId);
    if (this.handlers.has(channel)) return;
    this.handlers.set(channel, onRemoteUpdate);

    if (!this.ready) return; // se resuelve solo cuando connect() ya corrió

    await this.subscriber.subscribe(channel, (message) => {
      let envelope: BusEnvelope;
      try {
        envelope = JSON.parse(message);
      } catch {
        return; // mensaje corrupto/ajeno en el canal, se ignora
      }
      if (envelope.instanceId === INSTANCE_ID) return; // eco de esta misma instancia
      const handler = this.handlers.get(channel);
      if (handler) handler(Buffer.from(envelope.updateB64, "base64"));
    });
  }

  async unsubscribeRoom(roomId: string): Promise<void> {
    const channel = this.channelFor(roomId);
    if (!this.handlers.has(channel)) return;
    this.handlers.delete(channel);
    if (this.ready) {
      await this.subscriber.unsubscribe(channel);
    }
  }

  async disconnect(): Promise<void> {
    if (!this.ready) return;
    await Promise.all([this.publisher.quit(), this.subscriber.quit()]);
    this.ready = false;
  }
}
