import { startCrdtServer } from "./state/crdt_sync.js";

await startCrdtServer(Number(process.env.CRDT_PORT ?? 4444));
