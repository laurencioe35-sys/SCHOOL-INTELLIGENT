import React, { useState } from "react";
import { useSocket } from "../context/SocketContext";

interface SuggestedComponent { component_type: "object3d" | "formula" | "highlight"; payload: Record<string, unknown>; }
interface SuggestionProposal { id: string; component: SuggestedComponent; }
type PromptStatus = "idle" | "submitting" | "awaiting-result" | "ready" | "failed";
interface BoardObjectPayload { x: number; y: number; z: number; shape: "triangle" | "cube" | "sphere" | "generic"; color?: string; label?: string; }
interface BoardFormulaPayload { kind: "formula"; text: string; }
interface BoardHighlightPayload { kind: "highlight"; text: string; }

function toBoardObject(payload: Record<string, unknown>): BoardObjectPayload {
  const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : 0;
  const shape = payload.shape;
  return { x: number(payload.x), y: number(payload.y), z: number(payload.z), shape: shape === "triangle" || shape === "cube" || shape === "sphere" || shape === "generic" ? shape : "generic", ...(typeof payload.color === "string" ? { color: payload.color } : {}), ...(typeof payload.label === "string" ? { label: payload.label.slice(0, 160) } : {}) };
}

function toBoardComponent(suggestion: SuggestedComponent): BoardObjectPayload | BoardFormulaPayload | BoardHighlightPayload {
  if (suggestion.component_type === "object3d") return toBoardObject(suggestion.payload);
  const text = typeof suggestion.payload.text === "string" ? suggestion.payload.text.trim().slice(0, 500) : "";
  if (!text) throw new Error("The proposal has no publishable content.");
  return suggestion.component_type === "formula" ? { kind: "formula", text } : { kind: "highlight", text };
}

export function TeacherDashboard({ suggestion, chatMessage, onRequestSuggestion, onAuditPublication, onResolveSuggestion, promptStatus }: { suggestion: SuggestionProposal | null; chatMessage: string | null; onRequestSuggestion: (prompt: string) => Promise<void>; onAuditPublication: (component: SuggestedComponent) => Promise<void>; onResolveSuggestion: (suggestionId: string) => void; promptStatus: PromptStatus; }) {
  const { doc, connected } = useSocket();
  const [lastAction, setLastAction] = useState("");
  const [prompt, setPrompt] = useState("");
  const isBusy = promptStatus === "submitting" || promptStatus === "awaiting-result";
  async function requestSuggestion(event: React.FormEvent) {
    event.preventDefault();
    if (!prompt.trim()) return;
    try { await onRequestSuggestion(prompt.trim()); setPrompt(""); setLastAction("Prompt submitted. Waiting for the educational agent."); }
    catch (error) { setLastAction(error instanceof Error ? error.message : "The prompt could not be submitted."); }
  }
  async function acceptSuggestion() {
    if (!suggestion) return;
    try { await onAuditPublication(suggestion.component); doc.transact(() => doc.getMap("pizarra").set(`${suggestion.component.component_type}_${Date.now()}`, toBoardComponent(suggestion.component)), "local"); onResolveSuggestion(suggestion.id); setLastAction("Proposal approved and published to the shared blackboard."); }
    catch (error) { setLastAction(error instanceof Error ? error.message : "The proposal could not be published."); }
  }
  return <div className="teacher-dashboard">
    <div>Connection: {connected ? "live" : "offline"}</div>
    <form onSubmit={requestSuggestion}>
      <label htmlFor="agent-prompt">Create content for the 3D blackboard</label>
      <input id="agent-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Example: Show a blue triangle" disabled={isBusy} required />
      <button type="submit" disabled={isBusy}>{promptStatus === "submitting" ? "Submitting..." : promptStatus === "awaiting-result" ? "Generating..." : "Generate proposal"}</button>
    </form>
    {promptStatus === "awaiting-result" && <p role="status">The agent is preparing a proposal for review.</p>}
    {chatMessage && <div className="suggestion-card"><p>Asistente pedagógico</p><p>{chatMessage}</p></div>}
    {suggestion ? <div className="suggestion-card"><p>AI proposal: {suggestion.component.component_type}</p><p>{typeof suggestion.component.payload.text === "string" ? suggestion.component.payload.text : typeof suggestion.component.payload.label === "string" ? suggestion.component.payload.label : "3D object ready for review."}</p><button onClick={acceptSuggestion}>Approve and publish</button><button onClick={() => { onResolveSuggestion(suggestion.id); setLastAction("Proposal discarded."); }}>Discard</button></div> : promptStatus === "idle" && <p>No proposals pending.</p>}
    {lastAction && <p className="last-action">{lastAction}</p>}
  </div>;
}
