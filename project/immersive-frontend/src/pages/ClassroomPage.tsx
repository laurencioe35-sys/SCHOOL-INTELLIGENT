/**
 * Vista de aula: envuelve SceneContainer (compartido por ambos roles) y
 * decide qué panel lateral mostrar según el rol del usuario autenticado.
 * Esto es lo que reemplaza el App.tsx monolítico anterior, que solo
 * mostraba TeacherDashboard sin importar quién entrara.
 *
 * NUEVO: `suggestion` ya no es un `null` fijo. Se lee del mismo Y.Doc
 * compartido (Y.Map "ai_suggestions"), que es donde debería aterrizar
 * cada `ui_component` que el ai-agents-engine publica en su
 * `output_queue` (ver orchestrator/loop_engine.py). Ese último salto —
 * un proceso puente que tome los eventos de `output_queue` (Python) y
 * los escriba en este Y.Map (Node, vía multimedia-stream-server) — es
 * la pieza de infraestructura que todavía falta: hoy nada escribe en
 * "ai_suggestions" en producción, así que este panel seguirá mostrando
 * "Sin sugerencias pendientes" hasta que ese puente exista. Este cambio
 * es el lado CONSUMIDOR, ya listo para cuando el productor se conecte.
 */
import React, { useEffect, useState } from "react";
import { useParams, Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { SocketProvider, useSocket } from "../context/SocketContext";
import { SceneContainer } from "../canvas-3d/SceneContainer";
import { TeacherDashboard } from "../components/TeacherDashboard";
import { StudentDashboard } from "../components/StudentDashboard";
import { VideoMixer } from "../components/VideoMixer";
import { useLiveKitSession } from "../hooks/useLiveKitSession";

type BoardTool = "cube" | "sphere" | "triangle";

function BoardToolbar({
  value,
  onChange,
}: {
  value: BoardTool;
  onChange: (tool: BoardTool) => void;
}) {
  const tools: Array<{ id: BoardTool; label: string; color: string }> = [
    { id: "cube", label: "Cubo", color: "#4cc9ff" },
    { id: "sphere", label: "Esfera", color: "#9efc7a" },
    { id: "triangle", label: "Triángulo", color: "#ffc857" },
  ];

  return (
    <div
      style={{
        position: "absolute",
        top: 18,
        left: 18,
        display: "flex",
        gap: 10,
        background: "rgba(14, 18, 30, 0.72)",
        backdropFilter: "blur(8px)",
        border: "1px solid rgba(255,255,255,0.14)",
        borderRadius: 14,
        padding: 8,
        zIndex: 10,
      }}
    >
      {tools.map((tool) => (
        <button
          key={tool.id}
          onClick={() => onChange(tool.id)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 12px",
            borderRadius: 10,
            border: value === tool.id ? "1px solid rgba(255,255,255,0.5)" : "1px solid transparent",
            background: value === tool.id ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.03)",
            color: "#f5f7ff",
            cursor: "pointer",
          }}
        >
          <span style={{ width: 12, height: 12, borderRadius: tool.id === "sphere" ? "50%" : tool.id === "triangle" ? "0 0 0 0" : 3, background: tool.color, display: "inline-block" }} />
          {tool.label}
        </button>
      ))}
    </div>
  );
}

const CRDT_SERVER_URL = import.meta.env.VITE_CRDT_SERVER_URL ?? "ws://localhost:4444";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8200";

interface SuggestedComponent {
  component_type: "object3d" | "formula" | "highlight";
  payload: Record<string, unknown>;
}

/** Debe vivir DENTRO de <SocketProvider> para tener acceso al Y.Doc via useSocket(). */
function TeacherPanel() {
  const { doc } = useSocket();
  const [suggestion, setSuggestion] = useState<SuggestedComponent | null>(null);

  useEffect(() => {
    const map = doc.getMap<SuggestedComponent>("ai_suggestions");
    const sync = () => {
      // "latest" es la única clave que el productor debería escribir:
      // una sugerencia reemplaza a la anterior en vez de acumularse,
      // porque el profesor solo necesita revisar la más reciente.
      setSuggestion(map.get("latest") ?? null);
    };
    sync();
    map.observe(sync);
    return () => map.unobserve(sync);
  }, [doc]);

  return <TeacherDashboard suggestion={suggestion} />;
}

function ClassroomWorkspace({
  classroomId,
  isTeacher,
  user,
}: {
  classroomId: string;
  isTeacher: boolean;
  user: {
    token: string;
    userId: string;
    role: "student" | "teacher" | "admin";
  };
}) {
  const { connected } = useSocket();
  const [boardTool, setBoardTool] = useState<BoardTool>("cube");

  const liveKit = useLiveKitSession(classroomId, isTeacher, API_BASE_URL, user.token);

  return (
    <div style={{ display: "flex", height: "100vh", background: "#07111d" }}>
      <div style={{ flex: 1, position: "relative", background: "radial-gradient(circle at top, #0f213a, #09131d 56%)" }}>
        <div style={{ position: "absolute", top: 12, left: 20, zIndex: 10, color: "#dfe8ff", fontSize: 13 }}>
          Estado de conexión: {connected ? "🟢 conectado" : "🔴 desconectado"}
        </div>
        <BoardToolbar value={boardTool} onChange={setBoardTool} />
        <SceneContainer videoTrack={liveKit.videoTrack} activeTool={boardTool} />
        {isTeacher && <VideoMixer videoTrack={liveKit.videoTrack} />}
        {liveKit.status === "error" && (
          <div style={{ position: "absolute", top: 56, left: 18, color: "#ffb4b4", fontSize: 14 }}>
            Video no disponible: {liveKit.error}
          </div>
        )}
      </div>
      <div style={{ width: 340, background: "#0b1524", borderLeft: "1px solid rgba(255,255,255,0.08)" }}>
        {isTeacher ? (
          <TeacherPanel />
        ) : (
          <StudentDashboard apiBaseUrl={API_BASE_URL} authToken={user.token} studentId={user.userId} />
        )}
      </div>
    </div>
  );
}

export function ClassroomPage() {
  const { user } = useAuth();
  const { classroomId } = useParams<{ classroomId: string }>();
  const isTeacher = user?.role === "teacher" || user?.role === "admin";

  if (!user) return null;
  if (!classroomId) return <Navigate to="/aulas" replace />;

  return (
    <SocketProvider roomId={classroomId} serverUrl={CRDT_SERVER_URL} authToken={user.token}>
      <ClassroomWorkspace classroomId={classroomId} isTeacher={isTeacher} user={user} />
    </SocketProvider>
  );
}
