/**
 * Panel del alumno: vista de solo-lectura de lo que el profesor publica
 * en la pizarra 3D, más su propio perfil (notas, pensiones). A diferencia
 * de TeacherDashboard, el alumno NO puede aceptar/descartar sugerencias
 * de IA ni editar directamente el estado "oficial" del aula — solo
 * observa la pizarra compartida (que sí puede manipular con gestos de
 * exploración propios, como rotar la cámara, sin que eso cuente como
 * edición del contenido).
 *
 * No compilado/ejecutado en este entorno (mismo motivo que el resto del
 * frontend: requiere `npm install` + navegador real).
 */
import React, { useEffect, useState } from "react";
import { useSocket } from "../context/SocketContext";

interface StudentProfile {
  student: { id: string; full_name: string; email: string };
  classrooms: string[];
  grade_history: { classroom_name: string; score: number; created_at: string }[];
  average_score: number | null;
}

interface InvoiceSummary {
  id: string;
  concept: string;
  amount_cents: number;
  currency: string;
  status: string;
  due_date: string;
}

export function StudentDashboard({
  apiBaseUrl,
  authToken,
  studentId,
}: {
  apiBaseUrl: string;
  authToken: string;
  studentId: string;
}) {
  const { connected } = useSocket();
  const [profile, setProfile] = useState<StudentProfile | null>(null);
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const headers = { Authorization: `Bearer ${authToken}` };
        const [profileRes, invoicesRes] = await Promise.all([
          fetch(`${apiBaseUrl}/students/${studentId}/profile`, { headers }),
          fetch(`${apiBaseUrl}/billing/invoices/student/${studentId}`, { headers }),
        ]);
        if (!profileRes.ok) throw new Error("No se pudo cargar el perfil");
        setProfile(await profileRes.json());
        setInvoices(invoicesRes.ok ? await invoicesRes.json() : []);
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "Error desconocido");
      }
    }
    load();
  }, [apiBaseUrl, authToken, studentId]);

  const pendingInvoices = invoices.filter((i) => i.status !== "paid");

  return (
    <div className="student-dashboard">
      <div>Pizarra: {connected ? "🟢 en vivo" : "🔴 desconectada"}</div>

      {loadError && <p className="error">{loadError}</p>}

      {profile && (
        <section>
          <h3>{profile.student.full_name}</h3>
          <p>Promedio: {profile.average_score ?? "Sin notas aún"}</p>
          <ul>
            {profile.grade_history.map((g, i) => (
              <li key={i}>
                {g.classroom_name}: {g.score}
              </li>
            ))}
          </ul>
        </section>
      )}

      {pendingInvoices.length > 0 && (
        <section className="pending-invoices">
          <h4>Pensiones pendientes</h4>
          <ul>
            {pendingInvoices.map((inv) => (
              <li key={inv.id}>
                {inv.concept}: {(inv.amount_cents / 100).toFixed(2)} {inv.currency} — vence{" "}
                {new Date(inv.due_date).toLocaleDateString()}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
