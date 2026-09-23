/**
 * Contexto de React que mantiene la conexión persistente al servidor CRDT
 * (state/crdt_sync.ts en el backend) y expone el Y.Doc compartido al resto
 * de componentes (SceneContainer, TeacherDashboard).
 *
 * NOTA: este archivo no se compiló/ejecutó en este entorno (requeriría un
 * proyecto Vite completo con node_modules de React instalados). La lógica
 * de conexión (incluida la autenticación por token) es la misma que se
 * probó y funcionó del lado servidor
 * (multimedia-stream-server/state/crdt_sync_test.mjs), donde se verificó
 * que el servidor rechaza conexiones sin token o con token expirado.
 */
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import * as Y from "yjs";

interface SocketContextValue {
  doc: Y.Doc;
  connected: boolean;
  authError: string | null;
}

const SocketContext = createContext<SocketContextValue | null>(null);

export function SocketProvider({
  roomId,
  serverUrl,
  authToken,
  children,
}: {
  roomId: string;
  serverUrl: string;
  /** Token emitido por core-erp-backend al hacer login (ver auth.py). */
  authToken: string;
  children: React.ReactNode;
}) {
  const doc = useMemo(() => new Y.Doc(), [roomId]);
  const [connected, setConnected] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    const ws = new WebSocket(`${serverUrl}?room=${roomId}&token=${authToken}`);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setConnected(true);
      setAuthError(null);
    };
    ws.onclose = (event) => {
      setConnected(false);
      // El servidor cierra con código 401 si el token falta o expiró.
      if (event.code === 401 || event.reason?.includes("401")) {
        setAuthError("Sesión expirada o inválida. Vuelve a iniciar sesión.");
      }
    };
    ws.onmessage = (event) => {
      Y.applyUpdate(doc, new Uint8Array(event.data as ArrayBuffer));
    };

    const updateHandler = (update: Uint8Array, origin: unknown) => {
      if (origin === "local" && ws.readyState === WebSocket.OPEN) {
        ws.send(update);
      }
    };
    doc.on("update", updateHandler);

    return () => {
      doc.off("update", updateHandler);
      ws.close();
    };
  }, [doc, roomId, serverUrl, authToken]);

  return (
    <SocketContext.Provider value={{ doc, connected, authError }}>
      {children}
    </SocketContext.Provider>
  );
}

export function useSocket() {
  const ctx = useContext(SocketContext);
  if (!ctx) throw new Error("useSocket debe usarse dentro de <SocketProvider>");
  return ctx;
}
