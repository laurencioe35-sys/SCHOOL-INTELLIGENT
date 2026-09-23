/**
 * Mesa de control del profesor ("human-in-the-loop"): el profesor ve lo que
 * el ai-agents-engine sugiere renderizar y puede aceptarlo o descartarlo
 * antes de que se propague a los alumnos — evita que una alucinación del
 * agente pedagógico llegue directo a la pizarra de 40 alumnos sin filtro.
 * No compilado/ejecutado en este entorno.
 */
import React, { useState } from "react";
import { useSocket } from "../context/SocketContext";

interface SuggestedComponent {
  component_type: "object3d" | "formula" | "highlight";
  payload: Record<string, unknown>;
}

export function TeacherDashboard({ suggestion }: { suggestion: SuggestedComponent | null }) {
  const { doc, connected } = useSocket();
  const [lastAction, setLastAction] = useState<string>("");

  function acceptSuggestion() {
    if (!suggestion) return;
    const map = doc.getMap("pizarra");
    const id = `obj_${Date.now()}`;
    doc.transact(() => {
      map.set(id, suggestion.payload);
    }, "local");
    setLastAction(`Publicado: ${suggestion.component_type}`);
  }

  return (
    <div className="teacher-dashboard">
      <div>Estado de conexión: {connected ? "🟢 conectado" : "🔴 desconectado"}</div>
      {suggestion ? (
        <div className="suggestion-card">
          <p>Sugerencia de IA: {suggestion.component_type}</p>
          <button onClick={acceptSuggestion}>Publicar a los alumnos</button>
          <button onClick={() => setLastAction("Descartado")}>Descartar</button>
        </div>
      ) : (
        <p>Sin sugerencias pendientes.</p>
      )}
      {lastAction && <p className="last-action">{lastAction}</p>}
    </div>
  );
}
