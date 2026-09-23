/**
 * Conecta a la sala de LiveKit de un aula usando el token real que
 * mintea core-erp-backend (ver api/classrooms.py: POST /start para el
 * docente que inicia la clase, POST /join-token para quien se une a una
 * ya iniciada). Esto SÍ se compiló y type-checkeó en este entorno
 * (`npx tsc --noEmit` + `npx vite build`, ambos limpios) — lo que NO se
 * probó aquí es una conexión real a un servidor LiveKit (requiere una
 * sala LiveKit real corriendo en algún lado, self-hosted o LiveKit
 * Cloud; no hay ninguna en este sandbox). Ver
 * multimedia-stream-server/streaming/webrtc_handler.ts para el resto del
 * contrato del lado servidor (webhooks).
 */
import { useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, LocalTrack, RemoteTrack } from "livekit-client";

interface LiveKitSessionState {
  status: "idle" | "connecting" | "connected" | "unavailable" | "error";
  videoTrack: MediaStreamTrack | null;
  error: string | null;
}

interface StartOrJoinResponse {
  livekit_ws_url?: string | null;
  livekit_token?: string | null;
  ws_url?: string;
  token?: string;
}

/**
 * @param classroomId  Aula a la que conectarse.
 * @param isTeacher    Si true, llama a /start (crea la sesión y publica
 *                     cámara/micrófono); si false, llama a /join-token
 *                     (se suscribe solamente).
 * @param apiBaseUrl   Base del core-erp-backend.
 * @param authToken    JWT de sesión del usuario (mismo que AuthContext).
 */
export function useLiveKitSession(
  classroomId: string | null,
  isTeacher: boolean,
  apiBaseUrl: string,
  authToken: string | null
): LiveKitSessionState {
  const [state, setState] = useState<LiveKitSessionState>({
    status: "idle",
    videoTrack: null,
    error: null,
  });
  const roomRef = useRef<Room | null>(null);

  useEffect(() => {
    if (!classroomId || !authToken) return;
    let cancelled = false;

    async function connect() {
      setState({ status: "connecting", videoTrack: null, error: null });
      try {
        const endpoint = isTeacher
          ? `${apiBaseUrl}/classrooms/${classroomId}/start`
          : `${apiBaseUrl}/classrooms/${classroomId}/join-token`;
        const resp = await fetch(endpoint, {
          method: "POST",
          headers: { Authorization: `Bearer ${authToken}` },
        });

        if (resp.status === 503) {
          // Streaming de video deshabilitado (sin LIVEKIT_API_KEY/SECRET
          // en el ERP) — la clase sigue funcionando solo con
          // pizarra/CRDT, no debe tratarse como un error fatal.
          if (!cancelled) setState({ status: "unavailable", videoTrack: null, error: null });
          return;
        }
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          throw new Error(body.detail ?? `El ERP respondió ${resp.status} al pedir el token de LiveKit`);
        }

        const body: StartOrJoinResponse = await resp.json();
        const wsUrl = body.livekit_ws_url ?? body.ws_url;
        const token = body.livekit_token ?? body.token;
        if (!wsUrl || !token) {
          if (!cancelled) setState({ status: "unavailable", videoTrack: null, error: null });
          return;
        }

        const room = new Room();
        roomRef.current = room;

        room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
          if (cancelled) return;
          if (track.kind === Track.Kind.Video) {
            setState((prev) => ({ ...prev, status: "connected", videoTrack: track.mediaStreamTrack }));
          }
        });
        room.on(RoomEvent.LocalTrackPublished, (publication) => {
          if (cancelled) return;
          const track = publication.track as LocalTrack | undefined;
          if (track && track.kind === Track.Kind.Video) {
            setState((prev) => ({ ...prev, status: "connected", videoTrack: track.mediaStreamTrack ?? null }));
          }
        });
        room.on(RoomEvent.Disconnected, () => {
          if (!cancelled) setState((prev) => ({ ...prev, status: "idle", videoTrack: null }));
        });

        await room.connect(wsUrl, token);
        if (cancelled) {
          room.disconnect();
          return;
        }

        if (isTeacher) {
          await room.localParticipant.setCameraEnabled(true);
          await room.localParticipant.setMicrophoneEnabled(true);
        }

        if (!cancelled) setState((prev) => ({ ...prev, status: "connected" }));
      } catch (err) {
        if (!cancelled) {
          setState({ status: "error", videoTrack: null, error: err instanceof Error ? err.message : String(err) });
        }
      }
    }

    connect();
    return () => {
      cancelled = true;
      roomRef.current?.disconnect();
      roomRef.current = null;
    };
  }, [classroomId, isTeacher, apiBaseUrl, authToken]);

  return state;
}
