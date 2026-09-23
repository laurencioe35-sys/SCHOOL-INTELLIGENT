import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { DegradedModeManager, WhiteboardMode } from "./whiteboard/DegradedModeManager";
import { LiveCaptionsOverlay } from "./accessibility/LiveCaptionsOverlay";
import { ReplayTimelineScrubber } from "./accessibility/ReplayTimelineScrubber";

type DashboardSummary = {
  tenant_id: string;
  students: number;
  courses: number;
  enrollments: number;
  average_grade: number;
  health: string;
  generated_at: string;
};

type Course = {
  id: string;
  code: string;
  name: string;
  active: boolean;
};

type CurriculumCatalog = {
  gradeLevels: Array<{ id: string; code: string; name: string }>;
  subjects: Array<{ id: string; code: string; name: string; area: string }>;
  standards: Array<{ id: string; code: string; description: string; is_placeholder: boolean }>;
};

type AdmissionApplication = {
  id: string;
  applicant_name: string;
  grade_level_code: string;
  status: string;
  decision_reason: string | null;
  waitlist_position: number | null;
};

type StudentSummary = {
  id: string;
  first_name: string;
  last_name: string;
};

type GradeRecord = {
  id: string;
  score: number;
  course_id?: string;
  comment?: string | null;
  created_at?: string;
};

type PortalRole = "student" | "teacher" | "guardian" | "admin";

type Invoice = {
  id: string;
  tenant_id: string;
  student_id: string;
  concept: string;
  amount_cents: number;
  currency: string;
  due_date: string;
  status: string;
  paid_at: string | null;
  payment_reference: string | null;
  created_at: string;
};

type TrialBalanceRow = {
  account_id: string;
  code: string;
  name: string;
  balance_cents: number;
};

type LessonBoardStep = {
  title: string;
  explanation: string;
  keyFact: string;
  question: string;
  answer: string;
};

type AgentCycleResult = {
  stream_id?: string;
  core_pipeline: Record<string, unknown> | null;
  core_pipeline_error: string | null;
  agent_results: Array<{
    agent_name: string;
    ok: boolean;
    data?: {
      topic?: string;
      message?: string;
      questions?: Array<{ question: string; options: string[] }>;
      chunks_processed?: number;
      topics_covered?: string[];
      action_counts?: Record<string, number>;
    } | null;
    error: string | null;
    duration_ms: number;
  }>;
  transcription?: { text?: string; dispatch_mode?: "manual" };
};

type AgentBoardComponent = {
  component_type: "object3d" | "formula" | "highlight";
  payload: { text?: string; label?: string; shape?: string; color?: string };
};

type WhiteboardOperation = {
  operation_id: string;
  operation_type: string;
  payload: {
    points?: Array<{ x: number; y: number; pressure?: number }>;
    color?: string;
    tool?: string;
    component?: AgentBoardComponent;
    source_stream_id?: string;
  };
};

type PublishedAgentBoardContent = {
  sourceStreamId?: string;
  component: AgentBoardComponent;
};

function readAgentBoardComponent(value: unknown): AgentBoardComponent | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as { component_type?: unknown; payload?: unknown };
  if (!(["object3d", "formula", "highlight"] as string[]).includes(String(candidate.component_type))) return null;
  if (!candidate.payload || typeof candidate.payload !== "object") return null;
  return candidate as AgentBoardComponent;
}

function describeAgentResult(result: AgentCycleResult["agent_results"][number]): string {
  if (!result.ok) return result.error ?? "El agente no pudo completar su tarea.";
  const data = result.data;
  if (data?.message) return data.message;
  const question = data?.questions?.[0];
  if (question) return `${question.question} (${question.options.join(" · ")})`;
  if (typeof data?.chunks_processed === "number") return `Analizó ${data.chunks_processed} fragmento(s) de la sesión.`;
  return "Tarea completada sin contenido publicable para esta vista.";
}

export default function App() {
  const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const [token, setToken] = useState(() => localStorage.getItem("erp_access_token") ?? "");
  const [authRole, setAuthRole] = useState(() => localStorage.getItem("erp_role") ?? "");
  const [email, setEmail] = useState("admin@demo.erp");
  const [password, setPassword] = useState("Demo123!");
  const [tenantId, setTenantId] = useState("11111111-1111-4111-8111-111111111111");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [catalog, setCatalog] = useState<CurriculumCatalog>({
    gradeLevels: [],
    subjects: [],
    standards: [],
  });
  const [applications, setApplications] = useState<AdmissionApplication[]>([]);
  const [teacherAssignedCourses, setTeacherAssignedCourses] = useState<Course[]>([]);
  const [teacherCourseGrades, setTeacherCourseGrades] = useState<Record<string, GradeRecord[]>>({});
  const [guardianStudents, setGuardianStudents] = useState<StudentSummary[]>([]);
  const [guardianStudentGrades, setGuardianStudentGrades] = useState<Record<string, GradeRecord[]>>({});
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [trialBalance, setTrialBalance] = useState<TrialBalanceRow[]>([]);
  const [portalRole, setPortalRole] = useState<PortalRole>("student");
  const [selectedEntryRole, setSelectedEntryRole] = useState<PortalRole>("student");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Verificando API...");
  const [workspaceQuery, setWorkspaceQuery] = useState("");
  const [workspaceFilter, setWorkspaceFilter] = useState<"all" | "courses" | "applications">("all");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const boardManager = useMemo(() => new DegradedModeManager(), []);
  const [boardMode, setBoardMode] = useState<WhiteboardMode>(boardManager.currentMode);
  const [boardColor, setBoardColor] = useState("#7dd3fc");
  const [boardTool, setBoardTool] = useState<"pen" | "eraser">("pen");
  const [boardCaption, setBoardCaption] = useState("Sincronización lista");
  const [replayPosition, setReplayPosition] = useState(680);
  const [lessonStepIndex, setLessonStepIndex] = useState(0);
  const [showLessonAnswer, setShowLessonAnswer] = useState(false);
  const [sceneRotation, setSceneRotation] = useState({ x: -6, y: 18 });
  const [sceneZoom, setSceneZoom] = useState(1);
  const [agentPreparation, setAgentPreparation] = useState<"idle" | "preparing" | "ready">("idle");
  const [sceneDragging, setSceneDragging] = useState(false);
  const [boardInputEnabled, setBoardInputEnabled] = useState(true);
  const [touchSupported, setTouchSupported] = useState(false);
  const [inputDevice, setInputDevice] = useState<"mouse" | "touch" | "pen">("mouse");
  const [syncedOperationCount, setSyncedOperationCount] = useState(0);
  const [realtimeConnected, setRealtimeConnected] = useState(false);
  const [voiceState, setVoiceState] = useState<"idle" | "recording" | "uploading" | "accepted" | "error">("idle");
  const [voiceAutoSend, setVoiceAutoSend] = useState(true);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [agentInstruction, setAgentInstruction] = useState("");
  const [agentCommandStatus, setAgentCommandStatus] = useState("Listo para recibir una instrucción.");
  const [agentResults, setAgentResults] = useState<AgentCycleResult[]>([]);
  const [publishedAgentResultIds, setPublishedAgentResultIds] = useState<Set<string>>(() => new Set());
  const [publishedBoardContent, setPublishedBoardContent] = useState<PublishedAgentBoardContent | null>(null);
  const [isReadingBoardResponse, setIsReadingBoardResponse] = useState(false);
  const boardCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const boardSurfaceRef = useRef<HTMLDivElement | null>(null);
  const boardSocketRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const handledTranscriptionIds = useRef(new Set<string>());
  const currentStrokeRef = useRef<Array<{ x: number; y: number; pressure: number }>>([]);
  const whiteboardRoomId = "live-classroom-default";
  const drawingRef = useRef(false);
  const lastPointRef = useRef<{ x: number; y: number } | null>(null);
  const scenePointerRef = useRef<{ x: number; y: number } | null>(null);
  const [boardEvents] = useState([
    { event_id: "evt-1", event_type: "inicio", t_offset_ms: 0 },
    { event_id: "evt-2", event_type: "explicación", t_offset_ms: 320 },
    { event_id: "evt-3", event_type: "ejercicio", t_offset_ms: 780 },
    { event_id: "evt-4", event_type: "validación", t_offset_ms: 1340 },
    { event_id: "evt-5", event_type: "cierre", t_offset_ms: 1860 },
  ]);
  const lessonSteps: LessonBoardStep[] = [
    { title: "Idea central", explanation: "Un poliedro es un sólido limitado por caras planas poligonales.", keyFact: "Caras + aristas + vértices", question: "¿Qué elemento se forma cuando se encuentran dos caras?", answer: "Una arista." },
    { title: "Fórmula", explanation: "Para un cubo, el volumen se obtiene multiplicando la arista tres veces.", keyFact: "V = a³", question: "Si la arista mide 10 cm, ¿cuál es el volumen?", answer: "V = 10³ = 1.000 cm³." },
    { title: "Aplicación", explanation: "Relaciona la fórmula con un objeto cotidiano y verifica las unidades.", keyFact: "El volumen se expresa en unidades cúbicas", question: "¿Por qué no se expresa en centímetros cuadrados?", answer: "Porque mide el espacio en tres dimensiones." },
  ];
  const activeLessonStep = lessonSteps[lessonStepIndex];

  const availablePortalRoles: PortalRole[] = authRole === "teacher"
    ? ["teacher"]
    : authRole === "guardian"
      ? ["guardian"]
      : authRole === "admin"
        ? ["student", "teacher", "guardian", "admin"]
        : ["student"];

  function clearInvalidSession() {
    localStorage.removeItem("erp_access_token");
    localStorage.removeItem("erp_role");
    setToken("");
    setAuthRole("");
    setError("Tu sesión venció o ya no es válida. Inicia sesión de nuevo.");
    setStatus("Autenticación requerida");
  }

  useEffect(() => {
    let isMounted = true;

    async function loadDashboard() {
      try {
        if (!token) {
          setStatus("Autenticación requerida");
          return;
        }
        const [healthResponse, summaryResponse, coursesResponse, gradeLevelsResponse, subjectsResponse, standardsResponse, applicationsResponse, invoicesResponse, trialBalanceResponse] = await Promise.all([
          fetch(`${apiBaseUrl}/api/v1/health`),
          fetch(`${apiBaseUrl}/api/v1/dashboard/summary`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(authRole === "student" ? `${apiBaseUrl}/api/v1/students/me/courses` : authRole === "teacher" ? `${apiBaseUrl}/api/v1/teachers/me/courses` : authRole === "admin" ? `${apiBaseUrl}/api/v1/courses` : `${apiBaseUrl}/api/v1/guardians/me/students`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${apiBaseUrl}/api/v1/curriculum/grade-levels`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${apiBaseUrl}/api/v1/curriculum/subjects`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${apiBaseUrl}/api/v1/curriculum/standards`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          authRole === "student"
            ? Promise.resolve(new Response("[]", { status: 200 }))
            : fetch(`${apiBaseUrl}/api/v1/admissions/applications`, {
                headers: { Authorization: `Bearer ${token}` },
              }),
          fetch(`${apiBaseUrl}/api/v1/billing/invoices`, {
            headers: { Authorization: `Bearer ${token}` },
          }).catch(() => new Response("[]", { status: 200 })),
          fetch(`${apiBaseUrl}/api/v1/accounting/trial-balance`, {
            headers: { Authorization: `Bearer ${token}` },
          }).catch(() => new Response("[]", { status: 200 })),
        ]);

        if (!healthResponse.ok) {
          throw new Error("La API no responde correctamente.");
        }

        const health = await healthResponse.json();
        const protectedResponses = [summaryResponse, coursesResponse, gradeLevelsResponse, subjectsResponse, standardsResponse, applicationsResponse, invoicesResponse, trialBalanceResponse];
        if (protectedResponses.some((response) => response.status === 401)) {
          if (isMounted) clearInvalidSession();
          return;
        }
        if (protectedResponses.some((response) => !response.ok)) {
          throw new Error("No fue posible cargar el resumen del dashboard.");
        }

        const payload = (await summaryResponse.json()) as DashboardSummary;
        const coursePayload = (await coursesResponse.json()) as Course[];
        const gradeLevels = (await gradeLevelsResponse.json()) as CurriculumCatalog["gradeLevels"];
        const subjects = (await subjectsResponse.json()) as CurriculumCatalog["subjects"];
        const standards = (await standardsResponse.json()) as CurriculumCatalog["standards"];
        const applicationPayload = (await applicationsResponse.json()) as AdmissionApplication[];
        const invoicePayload = (await invoicesResponse.json()) as Invoice[];
        const balancePayload = (await trialBalanceResponse.json()) as TrialBalanceRow[];
        if (!isMounted) return;

        setSummary(payload);
        setCourses(coursePayload);
        setCatalog({ gradeLevels, subjects, standards });
        setApplications(applicationPayload);
        setInvoices(invoicePayload);
        setTrialBalance(balancePayload);
        setStatus(health.status === "ok" ? "API operativa" : "API en revisión");
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Error desconocido");
        setStatus("API no disponible");
      }
    }

    void loadDashboard();
    return () => {
      isMounted = false;
    };
  }, [apiBaseUrl, token, authRole]);

  useEffect(() => {
    if (!token || !["teacher", "guardian"].includes(authRole)) {
      setTeacherAssignedCourses([]);
      setTeacherCourseGrades({});
      setGuardianStudents([]);
      setGuardianStudentGrades({});
      return;
    }

    let isMounted = true;

    async function loadRolePortalData() {
      try {
        if (authRole === "teacher") {
          const response = await fetch(`${apiBaseUrl}/api/v1/teachers/me/courses`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!response.ok) {
            throw new Error("No fue posible cargar los cursos asignados.");
          }
          const teacherCourses = (await response.json()) as Course[];
          const gradesByCourse = await Promise.all(
            teacherCourses.map(async (course) => {
              const gradesResponse = await fetch(`${apiBaseUrl}/api/v1/teachers/me/courses/${course.id}/grades`, {
                headers: { Authorization: `Bearer ${token}` },
              });
              const grades = gradesResponse.ok ? ((await gradesResponse.json()) as GradeRecord[]) : [];
              return { courseId: course.id, grades };
            }),
          );
          if (!isMounted) return;
          setTeacherAssignedCourses(teacherCourses);
          setTeacherCourseGrades(Object.fromEntries(gradesByCourse.map(({ courseId, grades }) => [courseId, grades])));
          return;
        }

        const studentsResponse = await fetch(`${apiBaseUrl}/api/v1/guardians/me/students`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!studentsResponse.ok) {
          throw new Error("No fue posible cargar los estudiantes vinculados.");
        }
        const students = (await studentsResponse.json()) as StudentSummary[];
        const gradesByStudent = await Promise.all(
          students.map(async (student) => {
            const gradesResponse = await fetch(`${apiBaseUrl}/api/v1/guardians/me/students/${student.id}/grades`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            const grades = gradesResponse.ok ? ((await gradesResponse.json()) as GradeRecord[]) : [];
            return { studentId: student.id, grades };
          }),
        );
        if (!isMounted) return;
        setGuardianStudents(students);
        setGuardianStudentGrades(Object.fromEntries(gradesByStudent.map(({ studentId, grades }) => [studentId, grades])));
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Error desconocido");
      }
    }

    void loadRolePortalData();
    return () => {
      isMounted = false;
    };
  }, [apiBaseUrl, authRole, token]);

  useEffect(() => {
    if (availablePortalRoles.length && !availablePortalRoles.includes(portalRole)) {
      setPortalRole(availablePortalRoles[0]);
    }
  }, [availablePortalRoles, portalRole]);

  useEffect(() => {
    const canvas = boardCanvasRef.current;
    if (!canvas) return;

    const context = canvas.getContext("2d");
    if (!context) return;

    const resizeCanvas = () => {
      const ratio = window.devicePixelRatio || 1;
      const size = canvas.getBoundingClientRect();
      canvas.width = Math.max(280, size.width) * ratio;
      canvas.height = Math.max(220, size.height) * ratio;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.lineCap = "round";
      context.lineJoin = "round";
    };

    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
    return () => window.removeEventListener("resize", resizeCanvas);
  }, [boardCanvasRef]);

  useEffect(() => {
    if (!token) return;
    let isMounted = true;
    async function hydrateBoard() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/whiteboard/${whiteboardRoomId}/operations`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("No se pudo cargar la sala de pizarra.");
        const operations = (await response.json()) as WhiteboardOperation[];
        if (!isMounted) return;
        const canvas = boardCanvasRef.current;
        const context = canvas?.getContext("2d");
        if (!canvas || !context) return;
        const scaleX = canvas.width / canvas.clientWidth;
        const scaleY = canvas.height / canvas.clientHeight;
        for (const operation of operations) {
          if (operation.operation_type === "agent_component") {
            const component = readAgentBoardComponent(operation.payload.component);
            if (component) {
              setPublishedBoardContent({ component });
              if (typeof operation.payload.source_stream_id === "string") {
                setPublishedAgentResultIds((current) => new Set(current).add(operation.payload.source_stream_id as string));
              }
            }
            continue;
          }
          const points = operation.payload.points ?? [];
          if (points.length < 2) continue;
          context.save();
          context.strokeStyle = operation.payload.tool === "eraser" ? "#f9fbff" : operation.payload.color ?? "#7dd3fc";
          context.lineWidth = operation.payload.tool === "eraser" ? 22 : 4;
          context.globalCompositeOperation = operation.payload.tool === "eraser" ? "destination-out" : "source-over";
          context.beginPath();
          context.moveTo(points[0].x * scaleX, points[0].y * scaleY);
          for (const point of points.slice(1)) context.lineTo(point.x * scaleX, point.y * scaleY);
          context.stroke();
          context.restore();
        }
        setSyncedOperationCount(operations.length);
        setBoardCaption(operations.length ? `${operations.length} operaciones restauradas en la sala.` : "Sala lista para comenzar.");
      } catch {
        setBoardCaption("Sala local activa; no se pudo cargar el snapshot remoto.");
      }
    }
    void hydrateBoard();
    return () => { isMounted = false; };
  }, [apiBaseUrl, token]);

  useEffect(() => {
    if (!token) return;
    let isMounted = true;
    let timer: number | undefined;
    const loadAgentResults = async () => {
      let nextPollMs = 10_000;
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/agent/results?session_id=${encodeURIComponent(whiteboardRoomId)}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const results = (await response.json()) as AgentCycleResult[];
          if (isMounted) {
            setAgentResults(results);
            const manualTranscript = results.find((result) => result.stream_id && !handledTranscriptionIds.current.has(result.stream_id) && result.transcription?.dispatch_mode === "manual" && result.transcription.text);
            if (manualTranscript?.stream_id && manualTranscript.transcription?.text) {
              handledTranscriptionIds.current.add(manualTranscript.stream_id);
              setVoiceTranscript(manualTranscript.transcription.text);
              setAgentInstruction(manualTranscript.transcription.text);
              setAgentCommandStatus("Transcripción lista: revísala y pulsa Enviar a agentes.");
            }
          }
        } else if (response.status === 429) {
          const retryAfterSeconds = Number(response.headers.get("Retry-After"));
          nextPollMs = Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0
            ? retryAfterSeconds * 1000
            : 60_000;
        }
      } catch {
        // The command and voice paths remain usable while result polling recovers.
        nextPollMs = 10_000;
      }
      if (isMounted) timer = window.setTimeout(() => void loadAgentResults(), nextPollMs);
    };
    void loadAgentResults();
    return () => { isMounted = false; if (timer !== undefined) window.clearTimeout(timer); };
  }, [apiBaseUrl, token]);

  useEffect(() => {
    if (!token) return;
    const websocketBase = apiBaseUrl.replace(/^http/, "ws");
    const socket = new WebSocket(`${websocketBase}/api/v1/whiteboard/${whiteboardRoomId}/stream?token=${encodeURIComponent(token)}`);
    boardSocketRef.current = socket;
    socket.onopen = () => {
      setRealtimeConnected(true);
      setBoardCaption("Colaboración en tiempo real conectada.");
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as { type?: string; operations?: WhiteboardOperation[]; operation_type?: string; payload?: WhiteboardOperation["payload"] };
      if (message.type === "snapshot") {
        setSyncedOperationCount(message.operations?.length ?? 0);
        const latestComponentOperation = [...(message.operations ?? [])].reverse().find((operation) => operation.operation_type === "agent_component");
        const component = latestComponentOperation && readAgentBoardComponent(latestComponentOperation.payload.component);
        if (component) setPublishedBoardContent({ component });
      }
      if (message.type === "operation") {
        setSyncedOperationCount((count) => count + 1);
        if (message.operation_type === "agent_component") {
          const component = readAgentBoardComponent(message.payload?.component);
          if (component) setPublishedBoardContent({ component });
        }
      }
    };
    socket.onerror = () => setRealtimeConnected(false);
    socket.onclose = () => {
      setRealtimeConnected(false);
      boardSocketRef.current = null;
    };
    return () => {
      socket.close();
      boardSocketRef.current = null;
    };
  }, [apiBaseUrl, token]);

  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  useEffect(() => {
    const supportsTouch = navigator.maxTouchPoints > 0 || "ontouchstart" in window;
    setTouchSupported(supportsTouch);
    const detectInputDevice = (event: PointerEvent) => {
      if (event.pointerType === "touch" || event.pointerType === "pen" || event.pointerType === "mouse") {
        setInputDevice(event.pointerType);
      }
    };
    window.addEventListener("pointerdown", detectInputDevice, { passive: true });
    return () => window.removeEventListener("pointerdown", detectInputDevice);
  }, []);

  function updateBoardMode(nextMode: WhiteboardMode) {
    setBoardMode(nextMode);
    if (nextMode === "DEGRADED_LOCAL_ONLY") {
      boardManager.connectionLost();
      setBoardCaption("Modo local: trabajo seguro sin red.");
    } else if (nextMode === "DEGRADED_NO_AI") {
      boardManager.aiUnavailable();
      setBoardCaption("IA no disponible: dibujo libre activo.");
    } else {
      boardManager.reconnected(true);
      setBoardCaption("Conexión estable: colaboración y IA listas.");
    }
  }

  function changeLessonStep(nextIndex: number) {
    const safeIndex = Math.max(0, Math.min(nextIndex, lessonSteps.length - 1));
    setLessonStepIndex(safeIndex);
    setShowLessonAnswer(false);
    setBoardCaption(`Pizarra alimentada: ${lessonSteps[safeIndex].title}.`);
  }

  async function prepareClassWithAgents() {
    if (!token) {
      setAgentCommandStatus("Inicia sesión como profesor o administrador para activar los agentes.");
      return;
    }
    setAgentPreparation("preparing");
    changeLessonStep(0);
    setBoardCaption("Enviando la preparación de la lección a los agentes...");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/events/transcript`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ session_id: whiteboardRoomId, raw_text: "Prepara una explicación visual 3D sobre volumen de poliedros con una fórmula y un ejercicio.", priority: "high" }),
      });
      if (!response.ok) throw new Error("Los agentes no aceptaron la preparación.");
      setAgentPreparation("ready");
      setAgentCommandStatus("Preparación aceptada: esperando la respuesta del pipeline.");
    } catch (error) {
      setAgentPreparation("idle");
      setAgentCommandStatus(error instanceof Error ? error.message : "No se pudo preparar la clase.");
    }
  }

  function startSceneDrag(event: React.PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    scenePointerRef.current = { x: event.clientX, y: event.clientY };
    setSceneDragging(true);
  }

  function moveSceneDrag(event: React.PointerEvent<HTMLDivElement>) {
    const previous = scenePointerRef.current;
    if (!previous) return;
    setSceneRotation((current) => ({ x: Math.max(-55, Math.min(55, current.x - (event.clientY - previous.y) * 0.35)), y: current.y + (event.clientX - previous.x) * 0.35 }));
    scenePointerRef.current = { x: event.clientX, y: event.clientY };
  }

  function stopSceneDrag(event: React.PointerEvent<HTMLDivElement>) {
    scenePointerRef.current = null;
    setSceneDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function drawBoardStroke(start: { x: number; y: number }, end: { x: number; y: number }) {
    const canvas = boardCanvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const scaleX = canvas.width / canvas.clientWidth;
    const scaleY = canvas.height / canvas.clientHeight;
    context.strokeStyle = boardTool === "eraser" ? "#0f172a" : boardColor;
    context.lineWidth = boardTool === "eraser" ? 22 : 4;
    context.beginPath();
    context.moveTo(start.x * scaleX, start.y * scaleY);
    context.lineTo(end.x * scaleX, end.y * scaleY);
    context.stroke();
  }

  function handleBoardPointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!boardInputEnabled) return;
    const canvas = boardCanvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    if (event.pointerType === "touch" || event.pointerType === "pen" || event.pointerType === "mouse") {
      setInputDevice(event.pointerType);
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    drawingRef.current = true;
    lastPointRef.current = point;
    currentStrokeRef.current = [{ x: point.x, y: point.y, pressure: event.pressure || 0.5 }];
    if (boardTool === "eraser") {
      const context = canvas.getContext("2d");
      if (!context) return;
      context.save();
      context.globalCompositeOperation = "destination-out";
      context.beginPath();
      context.arc(point.x, point.y, 10, 0, Math.PI * 2);
      context.fill();
      context.restore();
    }
  }

  function handleBoardPointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!boardInputEnabled || !drawingRef.current || !lastPointRef.current) return;
    const canvas = boardCanvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const currentPoint = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    drawBoardStroke(lastPointRef.current, currentPoint);
    lastPointRef.current = currentPoint;
    currentStrokeRef.current.push({ x: currentPoint.x, y: currentPoint.y, pressure: event.pressure || 0.5 });
  }

  function handleBoardPointerUp(event?: React.PointerEvent<HTMLCanvasElement>) {
    const stroke = currentStrokeRef.current;
    drawingRef.current = false;
    lastPointRef.current = null;
    currentStrokeRef.current = [];
    if (stroke.length > 1) void persistBoardStroke(stroke, event?.pointerType ?? inputDevice);
    if (event && event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function clearBoardCanvas() {
    const canvas = boardCanvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    setBoardCaption("Lienzo limpio y listo para trabajar.");
  }

  async function toggleBoardFullscreen() {
    const surface = boardSurfaceRef.current;
    if (!surface) return;
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      return;
    }
    await surface.requestFullscreen();
  }

  async function persistBoardStroke(points: Array<{ x: number; y: number; pressure: number }>, pointerType: string) {
    if (!token) return;
    const operation = {
      operation_id: crypto.randomUUID(),
      operation_type: "stroke",
      payload: { points, tool: boardTool, color: boardColor, pointer_type: pointerType },
    };
    if (boardSocketRef.current?.readyState === WebSocket.OPEN) {
      boardSocketRef.current.send(JSON.stringify(operation));
      setBoardCaption("Trazo enviado a la sala en tiempo real.");
      return;
    }
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/whiteboard/${whiteboardRoomId}/operations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(operation),
      });
      if (!response.ok) throw new Error("No se pudo sincronizar el trazo.");
      setSyncedOperationCount((count) => count + 1);
      setBoardCaption("Trazo sincronizado en la sala de clase.");
    } catch {
      setBoardCaption("Trazo local guardado; se reintentará al recuperar la conexión.");
    }
  }

  async function publishAgentComponentToBoard() {
    const resultId = latestAgentResult?.stream_id;
    if (!token || !activeAgentComponent || !resultId || publishedAgentResultIds.has(resultId)) return;

    const operation = {
      operation_id: crypto.randomUUID(),
      operation_type: "agent_component",
      payload: { component: activeAgentComponent, source_stream_id: resultId },
    };
    try {
      if (boardSocketRef.current?.readyState === WebSocket.OPEN) {
        boardSocketRef.current.send(JSON.stringify(operation));
      } else {
        const response = await fetch(`${apiBaseUrl}/api/v1/whiteboard/${whiteboardRoomId}/operations`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify(operation),
        });
        if (!response.ok) throw new Error("No se pudo publicar el contenido del agente.");
      }
      setPublishedAgentResultIds((current) => new Set(current).add(resultId));
      setPublishedBoardContent({ sourceStreamId: resultId, component: activeAgentComponent });
      setSyncedOperationCount((count) => count + 1);
      setBoardCaption("Respuesta publicada en la pizarra compartida.");
      readBoardResponse();
    } catch (error) {
      setBoardCaption(error instanceof Error ? error.message : "No se pudo publicar el contenido del agente.");
    }
  }

  async function startVoiceCapture() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceState("error");
      setAgentCommandStatus("Este equipo no expone captura de micrófono en el navegador.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg"].find((candidate) => MediaRecorder.isTypeSupported(candidate));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
        setVoiceState("uploading");
        const audio = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        const formData = new FormData();
        formData.append("audio", audio, "class-command.webm");
          formData.append("session_id", whiteboardRoomId);
          formData.append("dispatch_mode", voiceAutoSend ? "auto" : "manual");
        try {
          const response = await fetch(`${apiBaseUrl}/api/v1/agent/events/audio`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: formData });
          if (!response.ok) throw new Error("El receptor de voz no aceptó el audio.");
          setVoiceState("accepted");
          setAgentCommandStatus(voiceAutoSend ? "Audio aceptado: transcripción y agentes en proceso." : "Audio aceptado: preparando transcripción para revisión.");
        } catch (error) {
          setVoiceState("error");
          setAgentCommandStatus(error instanceof Error ? error.message : "No se pudo enviar el audio.");
        }
      };
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      recorder.start();
      setVoiceState("recording");
      setAgentCommandStatus("Escuchando al profesor...");
    } catch {
      setVoiceState("error");
      setAgentCommandStatus("No se concedió acceso al micrófono.");
    }
  }

  function stopVoiceCapture() {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
  }

  function readBoardResponse() {
    if (!("speechSynthesis" in window)) {
      setAgentCommandStatus("Este navegador no ofrece lectura de voz. Puedes usar el chat y la pizarra normalmente.");
      return;
    }
    const component = publishedBoardContent?.component ?? activeAgentComponent;
    const explanation = latestTeacherResponse?.message
      || component?.payload.text
      || component?.payload.label
      || latestPipeline?.semantic_chunk?.text;
    if (!explanation) {
      setAgentCommandStatus("Aún no hay una respuesta del agente para leer.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(`Explicación para la pizarra. ${explanation}`);
    utterance.lang = "es-CO";
    utterance.rate = 0.95;
    utterance.onstart = () => setIsReadingBoardResponse(true);
    utterance.onend = () => setIsReadingBoardResponse(false);
    utterance.onerror = () => {
      setIsReadingBoardResponse(false);
      setAgentCommandStatus("No se pudo reproducir la explicación de voz.");
    };
    window.speechSynthesis.speak(utterance);
    setAgentCommandStatus("El agente está leyendo la explicación publicada.");
  }

  async function sendAgentInstruction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const instruction = agentInstruction.trim();
    if (!instruction || !token) return;
    setAgentCommandStatus("Enviando instrucción a los agentes...");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/events/transcript`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ session_id: whiteboardRoomId, raw_text: instruction, priority: "high" }),
      });
      if (!response.ok) throw new Error("El comando no fue aceptado por el receptor de agentes.");
      setAgentInstruction("");
      setAgentCommandStatus("Comando aceptado: agentes procesando la clase.");
    } catch (error) {
      setAgentCommandStatus(error instanceof Error ? error.message : "No se pudo enviar el comando.");
    }
  }

  const latestAgentResult = agentResults[0];
  const latestPipeline = latestAgentResult?.core_pipeline as { semantic_chunk?: { text?: string; topic?: string }; decision?: { action?: string; priority?: string }; ui_component?: { component_type?: string; payload?: { text?: string } } | null } | null;
  const activeAgentComponent = readAgentBoardComponent(latestPipeline?.ui_component);
  const visibleAgentComponent = publishedBoardContent?.component ?? activeAgentComponent;
  const liveTopic = latestPipeline?.semantic_chunk?.topic || "Esperando instrucción del profesor";
  const liveAction = latestPipeline?.decision?.action || "sin acción visual";
  const liveComponent = activeAgentComponent?.component_type || latestPipeline?.ui_component?.component_type || "pendiente";
  const latestQuiz = latestAgentResult?.agent_results.find((result) => result.agent_name === "content_generator_agent")?.data;
  const latestTeacherResponse = latestAgentResult?.agent_results.find((result) => result.agent_name === "teacher_response_agent")?.data;
  const latestQuestion = latestQuiz?.questions?.[0];

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const response = await fetch(`${apiBaseUrl}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: tenantId, email, password }),
    });
    if (!response.ok) {
      setError("Credenciales o tenant inválidos.");
      return;
    }
    const payload = (await response.json()) as { access_token: string; role: string };
    localStorage.setItem("erp_access_token", payload.access_token);
    localStorage.setItem("erp_role", payload.role);
    setToken(payload.access_token);
    setAuthRole(payload.role);
  }

  const normalizedWorkspaceQuery = workspaceQuery.trim().toLowerCase();
  const visibleCourses = courses.filter((course) =>
    !normalizedWorkspaceQuery || `${course.code} ${course.name}`.toLowerCase().includes(normalizedWorkspaceQuery),
  );
  const visibleApplications = applications.filter((application) =>
    !normalizedWorkspaceQuery || `${application.applicant_name} ${application.grade_level_code} ${application.status}`.toLowerCase().includes(normalizedWorkspaceQuery),
  );
  const overviewAverage = summary?.average_grade ?? 4.2;
  const overviewSubjects = courses.length || 8;
  const overviewAttendance = 79;
  const overviewFinanceStatus = invoices.length && invoices.every((invoice) => invoice.status === "paid") ? "Al día" : "Por revisar";

  async function refreshWorkspace() {
    setIsRefreshing(true);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/health`);
      if (!response.ok) throw new Error("La API no está disponible para actualizar el centro de control.");
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No fue posible actualizar los datos.");
      setIsRefreshing(false);
    }
  }

  function exportWorkspaceSnapshot() {
    const rows = [
      ["tipo", "identificador", "nombre", "estado"],
      ...visibleCourses.map((course) => ["curso", course.code, course.name, course.active ? "activo" : "inactivo"]),
      ...visibleApplications.map((application) => ["admisión", application.id, application.applicant_name, application.status]),
    ];
    const csv = rows.map((row) => row.map((value) => `"${value.replaceAll('"', '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `erp-centro-control-${new Date().toISOString().slice(0, 10)}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (!token) {
    const entryCards: Array<{ key: PortalRole; title: string; subtitle: string; icon: string }> = [
      { key: "student", title: "Estudiante", subtitle: "Notas, horario, asistencia, pagos", icon: "🎒" },
      { key: "teacher", title: "Profesor", subtitle: "Cursos, calificar, pizarra, asistencia", icon: "👩‍🏫" },
      { key: "guardian", title: "Acudiente", subtitle: "Seguimiento familiar y rendimiento", icon: "👨‍👩‍👧" },
      { key: "admin", title: "Administrativo", subtitle: "Matrículas, reportes, finanzas", icon: "📁" },
    ];

    return (
      <main className="landing-shell">
        <div className="landing-wrap">
          <div className="landing-logo">🎓</div>
          <h1>ERP Educativo Enterprise</h1>
          <p>Seleccione su portal de acceso · Multi-tenant · Control por rol</p>

          <div className="role-grid">
            {entryCards.map((card) => (
              <button
                key={card.key}
                type="button"
                className={selectedEntryRole === card.key ? "role-card active" : "role-card"}
                onClick={() => setSelectedEntryRole(card.key)}
              >
                <span className="role-icon">{card.icon}</span>
                <b>{card.title}</b>
                <span>{card.subtitle}</span>
              </button>
            ))}
          </div>

          <section className="auth-panel">
            <div className="auth-header">
              <span className="eyebrow">ACCESO</span>
              <h2>{selectedEntryRole === "student" ? "Portal estudiantil" : selectedEntryRole === "teacher" ? "Portal docente" : selectedEntryRole === "guardian" ? "Portal acudiente" : "Portal administrativo"}</h2>
            </div>
            {error && <div className="error">{error}</div>}
            <form className="auth-form" onSubmit={handleLogin}>
              <label>Tenant ID<input value={tenantId} onChange={(event) => setTenantId(event.target.value)} required /></label>
              <label>Correo<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
              <label>Contraseña<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
              <button className="auth-submit" type="submit">Iniciar sesión</button>
            </form>
          </section>
        </div>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">🎓</div>
          <div>
            <b>ERP Educativo</b>
            <span>Portal institucional</span>
          </div>
        </div>

        <nav className="main-nav" aria-label="Navegación principal">
          <div className="nav-label">ESCRITORIO</div>
          <a className="nav-link active" href="#dashboard"><span>🏠</span>Inicio</a>
          <a className="nav-link" href="#academics"><span>📚</span>Mis calificaciones</a>
          <a className="nav-link" href="#schedule"><span>🗓️</span>Horario</a>
          <a className="nav-link" href="#attendance"><span>✅</span>Asistencia</a>
          <a className="nav-link" href="#payments"><span>💳</span>Pagos y estado</a>
          <a className="nav-link" href="#resources"><span>📁</span>Recursos</a>
        </nav>
      </aside>

      <main className="workspace-main">
        <header className="topbar">
          <div>
            <span className="eyebrow">ERP EDUCATIVO</span>
            <h1>Panel institucional</h1>
          </div>
          <div className="top-actions">
            <button className="icon-button" type="button" aria-label="Notificaciones">🔔</button>
            <div className="user-pill">
              <div className="avatar">AU</div>
              <div>
                <b>{authRole === "admin" ? "Admin" : authRole === "teacher" ? "Profesor" : authRole === "guardian" ? "Acudiente" : "Estudiante"}</b>
                <span>{status}</span>
              </div>
            </div>
          </div>
        </header>

        <nav className="portal-nav" aria-label="Portales educativos">
          {availablePortalRoles.map((role) => (
            <button
              className={portalRole === role ? "portal-tab active" : "portal-tab"}
              key={role}
              onClick={() => setPortalRole(role)}
              aria-current={portalRole === role ? "page" : undefined}
            >
              {role === "student" ? "Estudiante" : role === "teacher" ? "Profesor" : role === "guardian" ? "Acudiente" : "Administrativo"}
            </button>
          ))}
        </nav>

        {error && <div className="error">{error}</div>}

        <section className="panel interactive-board" id="whiteboard" aria-labelledby="interactive-board-heading">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">PIZARRA FUNCIONAL</span>
              <h2 id="interactive-board-heading">Dibuja, repasa y trabaja sin perder la clase</h2>
            </div>
            <span className="count-badge">{boardMode.replaceAll("_", " ")}</span>
          </div>
          <div className="board-controls" role="toolbar" aria-label="Herramientas de pizarra">
            <button type="button" className={boardTool === "pen" ? "board-tool active" : "board-tool"} onClick={() => setBoardTool("pen")} aria-pressed={boardTool === "pen"}>✎ Lápiz</button>
            <button type="button" className={boardTool === "eraser" ? "board-tool active" : "board-tool"} onClick={() => setBoardTool("eraser")} aria-pressed={boardTool === "eraser"}>⌫ Borrador</button>
            <label className="board-color">Color <input type="color" value={boardColor} onChange={(event) => setBoardColor(event.target.value)} disabled={boardTool === "eraser"} /></label>
            <button type="button" className="board-tool" onClick={clearBoardCanvas}>Limpiar</button>
            <span className="board-control-spacer" />
            <button type="button" className={voiceState === "recording" ? "board-mode active recording" : "board-mode"} onClick={() => voiceState === "recording" ? stopVoiceCapture() : void startVoiceCapture()}>{voiceState === "recording" ? "■ Detener voz" : "🎙 Voz del profesor"}</button>
            <label className="board-mode"><input type="checkbox" checked={voiceAutoSend} onChange={(event) => setVoiceAutoSend(event.target.checked)} /> Envío automático</label>
            <button type="button" className={boardInputEnabled ? "board-mode active" : "board-mode"} onClick={() => setBoardInputEnabled((current) => !current)} aria-pressed={boardInputEnabled}>{boardInputEnabled ? "Interacción activa" : "Activar interacción"}</button>
            <button type="button" className="board-mode" onClick={() => void toggleBoardFullscreen()}>⛶ Pantalla completa</button>
            <button type="button" className={boardMode === "ONLINE_FULL" ? "board-mode active" : "board-mode"} onClick={() => updateBoardMode("ONLINE_FULL")}>Conectada</button>
            <button type="button" className={boardMode === "DEGRADED_LOCAL_ONLY" ? "board-mode active" : "board-mode"} onClick={() => updateBoardMode("DEGRADED_LOCAL_ONLY")}>Local</button>
            <button type="button" className={boardMode === "DEGRADED_NO_AI" ? "board-mode active" : "board-mode"} onClick={() => updateBoardMode("DEGRADED_NO_AI")}>Sin IA</button>
          </div>
          <div className="interactive-board-grid" ref={boardSurfaceRef}>
            <div className="canvas-stage">
              <canvas
                ref={boardCanvasRef}
                className="drawing-canvas"
                aria-label="Lienzo de pizarra interactiva"
                onPointerDown={handleBoardPointerDown}
                onPointerMove={handleBoardPointerMove}
                onPointerUp={handleBoardPointerUp}
                onPointerCancel={handleBoardPointerUp}
                onPointerLeave={(event) => { if (drawingRef.current) handleBoardPointerUp(event); }}
              />
              <LiveCaptionsOverlay caption={boardCaption} isActive={boardMode === "ONLINE_FULL"} />
            </div>
            <aside className="board-status-panel">
              <h3>Estado de la clase</h3>
              <div className="board-status-row"><span>Modo</span><strong>{boardMode.replaceAll("_", " ")}</strong></div>
              <div className="board-status-row"><span>Herramienta</span><strong>{boardTool === "pen" ? "Lápiz" : "Borrador"}</strong></div>
              <div className="board-status-row"><span>Color</span><strong>{boardTool === "eraser" ? "Borrado" : boardColor}</strong></div>
              <p>{touchSupported ? "Táctil disponible: toca y arrastra con el dedo o lápiz." : "Usa mouse o lápiz digital; el modo táctil se activará automáticamente en pantallas compatibles."}</p>
              <div className="board-status-row"><span>Entrada detectada</span><strong>{inputDevice === "touch" ? "Táctil" : inputDevice === "pen" ? "Lápiz" : "Mouse"}</strong></div>
              <div className="board-status-row"><span>Tiempo real</span><strong>{realtimeConnected ? "Conectado" : "Fallback REST"}</strong></div>
              <div className="board-status-row"><span>Operaciones sincronizadas</span><strong>{syncedOperationCount}</strong></div>
              <form className="agent-command-form" onSubmit={(event) => void sendAgentInstruction(event)}>
                <label htmlFor="agent-instruction">Comando a los agentes {voiceTranscript && "· transcripción es-CO lista"}</label>
                <input id="agent-instruction" value={agentInstruction} onChange={(event) => setAgentInstruction(event.target.value)} placeholder="Ej. prepara una explicación del volumen" />
                <button type="submit">Enviar a agentes</button>
                {voiceTranscript && <button type="button" onClick={() => { setVoiceTranscript(""); setAgentInstruction(""); }}>Descartar transcripción</button>}
                <small>{agentCommandStatus}</small>
              </form>
              <div className="agent-result-panel" aria-live="polite">
                <div className="lesson-feed-heading"><span>Respuesta real de agentes</span><b>{agentResults.length}</b></div>
                {latestAgentResult ? (
                  <>
                    <div className="agent-result-list">
                      {latestAgentResult.agent_results.map((result) => (
                        <div className="agent-result-row" key={result.agent_name}>
                          <span className={result.ok ? "agent-ok" : "agent-fail"}>{result.ok ? "OK" : "ERROR"}</span>
                          <strong>{result.agent_name}</strong>
                          <small>{result.error ?? `${Math.round(result.duration_ms)} ms`}</small>
                        </div>
                      ))}
                    </div>
                    <small className={latestAgentResult.core_pipeline_error ? "agent-fail-text" : "agent-ok-text"}>
                      {latestAgentResult.core_pipeline_error ? `Core pipeline: ${latestAgentResult.core_pipeline_error}` : latestAgentResult.core_pipeline ? "Core pipeline completado." : "Core pipeline pendiente."}
                    </small>
                  </>
                ) : <small>Aún no hay resultados para esta sala.</small>}
              </div>
              <div className="lesson-feed" aria-label="Contenido pedagógico de la lección">
                <div className="lesson-feed-heading"><span>Alimentación de clase</span><b>{lessonStepIndex + 1}/{lessonSteps.length}</b></div>
                <h4>{activeLessonStep.title}</h4>
                <p>{activeLessonStep.explanation}</p>
                <div className="lesson-key-fact">{activeLessonStep.keyFact}</div>
                <div className="lesson-question"><strong>Pregunta</strong><span>{activeLessonStep.question}</span></div>
                {showLessonAnswer && <div className="lesson-answer"><strong>Respuesta guiada</strong><span>{activeLessonStep.answer}</span></div>}
                <button type="button" className="lesson-answer-button" onClick={() => setShowLessonAnswer((current) => !current)}>{showLessonAnswer ? "Ocultar respuesta" : "Ver respuesta"}</button>
                <div className="lesson-step-actions"><button type="button" onClick={() => changeLessonStep(lessonStepIndex - 1)} disabled={lessonStepIndex === 0}>Anterior</button><button type="button" onClick={() => changeLessonStep(lessonStepIndex + 1)} disabled={lessonStepIndex === lessonSteps.length - 1}>Siguiente</button></div>
              </div>
              <ReplayTimelineScrubber events={boardEvents} positionMs={replayPosition} onSeek={setReplayPosition} />
            </aside>
          </div>
        </section>

        <section className="student-overview" id="overview" aria-labelledby="overview-heading">
          {status !== "API operativa" && (
            <div className="demo-notice" role="status">
              <span aria-hidden="true">⚠</span>
              <strong>Sin backend.</strong> La información mostrada es de demostración y se reemplaza automáticamente al conectar la API.
            </div>
          )}
          <div className="overview-ticker" aria-label="Resumen de novedades">
            <span>Promedio actual: <b>{overviewAverage.toFixed(1)} / 5.0</b></span>
            <span>▣ Simulacro institucional: en 9 días</span>
            <span>⚑ Entrega de proyecto: viernes</span>
            <span>▰ Pensión de octubre: al día</span>
          </div>
          <div className="overview-heading">
            <div>
              <span className="eyebrow">EDUERP · COLEGIO SAN MARTÍN</span>
              <h2 id="overview-heading">Inicio</h2>
              <p>Una lectura clara de tu progreso académico y tus próximas tareas.</p>
            </div>
            <span className="overview-date">Sesión {portalRole}</span>
          </div>
          <div className="overview-stats">
            <article><span>Promedio general</span><strong>{overviewAverage.toFixed(1)}</strong><small>+0.3 vs periodo anterior</small><b aria-hidden="true">🎯</b></article>
            <article><span>Asistencia</span><strong>{overviewAttendance}%</strong><small>2 faltas justificadas</small><b aria-hidden="true">✅</b></article>
            <article><span>Materias activas</span><strong>{overviewSubjects}</strong><small>2 con entrega esta semana</small><b aria-hidden="true">▣</b></article>
            <article><span>Estado financiero</span><strong>{overviewFinanceStatus}</strong><small>Próximo pago: 5 nov</small><b aria-hidden="true">▤</b></article>
          </div>
          <div className="overview-charts">
            <article className="overview-chart-card">
              <div className="overview-card-heading"><h3>Evolución de mi promedio</h3><span>Demo</span></div>
              <div className="line-chart" aria-label="Evolución del promedio de febrero a octubre">
                <div className="chart-grid" />
                <svg viewBox="0 0 700 180" role="img" aria-label="Línea de promedio ascendente">
                  <polyline points="12,138 100,130 188,122 276,116 364,124 452,106 540,116 628,98 688,106" fill="none" stroke="currentColor" strokeWidth="4" />
                  <polyline points="12,138 100,130 188,122 276,116 364,124 452,106 540,116 628,98 688,106 688,170 12,170" fill="currentColor" opacity="0.14" />
                </svg>
                <div className="chart-labels"><span>Feb</span><span>Mar</span><span>Abr</span><span>May</span><span>Jun</span><span>Jul</span><span>Ago</span><span>Sep</span><span>Oct</span></div>
              </div>
            </article>
            <article className="overview-chart-card subject-chart-card">
              <div className="overview-card-heading"><h3>Desempeño por materia</h3><span>Demo</span></div>
              <div className="subject-radar" aria-label="Desempeño por materia">
                <div className="radar-ring ring-one" /><div className="radar-ring ring-two" /><div className="radar-ring ring-three" />
                <div className="radar-shape" />
                <span className="radar-label top">Matemáticas</span><span className="radar-label right">Física</span><span className="radar-label bottom-right">Química</span><span className="radar-label bottom-left">Español</span><span className="radar-label left">Historia</span>
              </div>
            </article>
          </div>
          <div className="overview-quick-links">
            <div className="overview-card-heading"><h3>Accesos rápidos</h3><span>6 herramientas</span></div>
            <div className="quick-link-grid">
              {[['▥', 'Boletín', 'Consulta y descarga tu boletín'], ['▦', 'Horario', 'Clases, aulas y docentes'], ['▤', 'Pagos', 'Estado de cuenta y recibos'], ['▧', 'Biblioteca', 'Recursos y material de apoyo'], ['✎', 'Pizarra', 'Clase interactiva en tiempo real'], ['▣', 'Mensajes', 'Comunicación con docentes']].map(([icon, title, description]) => (
                <button className="quick-link" type="button" key={title} onClick={() => setWorkspaceQuery(title)}><span>{icon}</span><strong>{title}</strong><small>{description}</small></button>
              ))}
            </div>
          </div>
        </section>

        <section className="kpis" id="dashboard">
          <article className="kpi">
            <div className="lb"><span>Estudiantes</span><i>👥</i></div>
            <div className="v">{summary?.students ?? 0}</div>
            <div className="d"><span className="up">▲</span> Gestión multi-tenant</div>
          </article>
          <article className="kpi">
            <div className="lb"><span>Cursos</span><i>📚</i></div>
            <div className="v">{summary?.courses ?? 0}</div>
            <div className="d"><span className="up">▲</span> Catálogo activo</div>
          </article>
          <article className="kpi">
            <div className="lb"><span>Promedio</span><i>📈</i></div>
            <div className="v">{summary ? summary.average_grade.toFixed(1) : "0.0"}</div>
            <div className="d"><span className="up">▲</span> Rendimiento general</div>
          </article>
        </section>

        <section className="panel command-center" aria-labelledby="command-center-heading">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">CENTRO DE CONTROL</span>
              <h2 id="command-center-heading">Encuentra y comparte lo importante</h2>
            </div>
            <div className="command-actions">
              <button className="tool-button" type="button" onClick={() => void refreshWorkspace()} disabled={isRefreshing}>
                {isRefreshing ? "Actualizando..." : "↻ Actualizar"}
              </button>
              <button className="tool-button primary" type="button" onClick={exportWorkspaceSnapshot}>
                ↓ Exportar CSV
              </button>
            </div>
          </div>
          <div className="command-toolbar">
            <label className="search-field">
              <span aria-hidden="true">⌕</span>
              <input value={workspaceQuery} onChange={(event) => setWorkspaceQuery(event.target.value)} placeholder="Buscar cursos, solicitudes o estados" />
            </label>
            <div className="filter-group" role="group" aria-label="Filtrar centro de control">
              {(["all", "courses", "applications"] as const).map((filter) => (
                <button key={filter} type="button" className={workspaceFilter === filter ? "filter-button active" : "filter-button"} onClick={() => setWorkspaceFilter(filter)}>
                  {filter === "all" ? "Todo" : filter === "courses" ? "Cursos" : "Admisiones"}
                </button>
              ))}
            </div>
          </div>
          <div className="command-results">
            {(workspaceFilter === "all" || workspaceFilter === "courses") && visibleCourses.slice(0, 4).map((course) => (
              <div className="command-result" key={`command-course-${course.id}`}>
                <span className="result-icon">📚</span>
                <div><strong>{course.name}</strong><small>{course.code} · Curso activo</small></div>
                <span className="result-state">Listo</span>
              </div>
            ))}
            {(workspaceFilter === "all" || workspaceFilter === "applications") && visibleApplications.slice(0, 4).map((application) => (
              <div className="command-result" key={`command-application-${application.id}`}>
                <span className="result-icon">◎</span>
                <div><strong>{application.applicant_name}</strong><small>{application.grade_level_code} · Solicitud de admisión</small></div>
                <span className={`result-state status-${application.status}`}>{application.status}</span>
              </div>
            ))}
            {((workspaceFilter === "courses" && visibleCourses.length === 0) || (workspaceFilter === "applications" && visibleApplications.length === 0) || (workspaceFilter === "all" && visibleCourses.length === 0 && visibleApplications.length === 0)) && (
              <p className="empty-state">No hay resultados para esta búsqueda.</p>
            )}
          </div>
        </section>

        <div className="grid g2">
          <section className="panel">
            <div className="ph">
              <h3>Estado del sistema</h3>
              <span className="sub">{status}</span>
            </div>
            <div className="metrics">
              <div>
                <label>Matrículas</label>
                <strong>{summary?.enrollments ?? 0}</strong>
              </div>
              <div>
                <label>Salud</label>
                <strong>{summary?.health ?? "pending"}</strong>
              </div>
              <div>
                <label>Tenant</label>
                <strong>{summary?.tenant_id ?? "n/a"}</strong>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="ph">
              <h3>Operación financiera</h3>
              <span className="sub">Facturas y cobranza</span>
            </div>
            <div className="metrics">
              <div>
                <label>Facturas</label>
                <strong>{invoices.length}</strong>
              </div>
              <div>
                <label>Pagadas</label>
                <strong>{invoices.filter((item) => item.status === "paid").length}</strong>
              </div>
              <div>
                <label>Saldo</label>
                <strong>{trialBalance.reduce((sum, row) => sum + row.balance_cents, 0).toLocaleString("es-PE")}</strong>
              </div>
            </div>
          </section>
        </div>

        <section className="panel curriculum-panel" id="academics">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">CURRÍCULO</span>
              <h2>Oferta académica activa</h2>
            </div>
            <span className="count-badge">{courses.length} cursos</span>
          </div>
          {courses.length === 0 ? (
            <p className="empty-state">No hay cursos activos configurados para este tenant.</p>
          ) : (
            <div className="course-list">
              {courses.map((course) => (
                <div className="course-row" key={course.id}>
                  <span className="course-code">{course.code}</span>
                  <strong>{course.name}</strong>
                  <span className="course-status">Activo</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="catalog-grid" aria-label="Catálogos curriculares">
          <article className="catalog-card">
            <span className="catalog-kicker">Niveles</span>
            <strong>{catalog.gradeLevels.length}</strong>
            <small>{catalog.gradeLevels.length ? catalog.gradeLevels.map((level) => level.name).join(", ") : "Sin niveles configurados"}</small>
          </article>
          <article className="catalog-card">
            <span className="catalog-kicker">Materias</span>
            <strong>{catalog.subjects.length}</strong>
            <small>{catalog.subjects.length ? catalog.subjects.map((subject) => subject.name).join(", ") : "Sin materias configuradas"}</small>
          </article>
          <article className="catalog-card">
            <span className="catalog-kicker">Estándares</span>
            <strong>{catalog.standards.length}</strong>
            <small>{catalog.standards.some((standard) => standard.is_placeholder) ? "Incluye placeholders de desarrollo" : "Catálogo listo para publicación"}</small>
          </article>
        </section>

        <section className="panel admissions-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">ADMISIONES</span>
              <h2>Solicitudes recientes</h2>
            </div>
            <span className="count-badge">{applications.length} solicitudes</span>
          </div>
          {applications.length === 0 ? (
            <p className="empty-state">No hay solicitudes registradas para este tenant.</p>
          ) : (
            <div className="course-list">
              {applications.map((application) => (
                <div className="course-row" key={application.id}>
                  <span className={`admission-status status-${application.status}`}>{application.status}</span>
                  <div>
                    <strong>{application.applicant_name}</strong>
                    <small>{application.decision_reason ?? "Sin decisión registrada"}</small>
                  </div>
                  <span className="course-code">{application.waitlist_position ? `Lista #${application.waitlist_position}` : `Grado ${application.grade_level_code}`}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="panel board-panel board-reference" aria-labelledby="board-heading">
          <div className="board-reference-shell">
            <aside className="reference-sidebar">
              <div className="reference-sidebar-header">
                <h3>Chat interno · loop de agentes</h3>
              </div>

              <div className="reference-feed">
                <div className="reference-message teacher">
                  <div className="reference-avatar">P</div>
                  <div className="reference-bubble">
                    <span className="reference-who">Profesor</span>
                    {latestPipeline?.semantic_chunk?.text || "Escribe una instrucción para iniciar la colaboración."}
                  </div>
                </div>

                <div className="reference-agent-label">Propuestas de agentes</div>
                {latestAgentResult ? latestAgentResult.agent_results.map((result) => (
                  <div className="reference-agent-card" key={result.agent_name}>
                    <div className="reference-agent-name">{result.agent_name}</div>
                    <div className="reference-agent-body"><strong>{result.ok ? "completado" : "error"}</strong> — {describeAgentResult(result)}</div>
                  </div>
                )) : <div className="reference-agent-card"><div className="reference-agent-name">pipeline</div><div className="reference-agent-body">Aún no hay una respuesta real de agentes.</div></div>}
              </div>

                {latestQuestion && (
                  <div className="reference-message agent" aria-live="polite">
                    <div className="reference-avatar">IA</div>
                    <div className="reference-bubble">
                      <span className="reference-who">Asistente pedagÃ³gico · {latestQuiz?.topic ?? liveTopic}</span>
                      <strong>{latestQuestion.question}</strong>
                      <div className="reference-agent-body">{latestQuestion.options.join(" · ")}</div>
                    </div>
                  </div>
                )}

                {latestTeacherResponse?.message && (
                  <div className="reference-message agent" aria-live="polite">
                    <div className="reference-avatar">IA</div>
                    <div className="reference-bubble">
                      <span className="reference-who">Asistente pedagógico · {latestTeacherResponse.topic ?? liveTopic}</span>
                      <strong>{latestTeacherResponse.message}</strong>
                    </div>
                  </div>
                )}

              <form className="reference-composer" onSubmit={(event) => void sendAgentInstruction(event)}>
                <input value={agentInstruction} onChange={(event) => setAgentInstruction(event.target.value)} placeholder="Habla como el profesor…" aria-label="Instrucción para los agentes" />
                <button type="button" className={voiceState === "recording" ? "voice-control recording" : "voice-control"} onClick={() => voiceState === "recording" ? stopVoiceCapture() : void startVoiceCapture()} aria-pressed={voiceState === "recording"}>{voiceState === "recording" ? "Detener voz" : "🎙 Dictar"}</button>
                <button type="submit" disabled={!agentInstruction.trim()}>Enviar</button>
              </form>
            </aside>

            <div className="reference-main-board">
              <div className="reference-topbar">
                <div className="reference-brand"><span className="reference-dot" /> Pizarra del Maestro · Lección 3D</div>
                <div className="reference-badges">
                  <span className="reference-gesture">{sceneDragging ? "Rotando escena" : "Arrastra para rotar"}</span>
                  <span className={realtimeConnected ? "reference-badge live" : "reference-badge"}><span className="reference-pulse" /> {realtimeConnected ? "Sala en tiempo real" : "Reconectando sala"}</span>
                </div>
                <div className="scene-actions" aria-label="Controles de escena 3D">
                  <button type="button" onClick={prepareClassWithAgents}>{agentPreparation === "preparing" ? "Preparando..." : agentPreparation === "ready" ? "Clase lista" : "Preparar clase"}</button>
                  <button type="button" className={isReadingBoardResponse ? "voice-control reading" : "voice-control"} onClick={readBoardResponse} disabled={!visibleAgentComponent && !latestTeacherResponse?.message} aria-pressed={isReadingBoardResponse}>{isReadingBoardResponse ? "🔊 Leyendo..." : "🔊 Leer respuesta"}</button>
                  <button type="button" onClick={() => setSceneRotation((current) => ({ ...current, y: current.y + 18 }))}>↻ Rotar</button>
                  <button type="button" onClick={() => setSceneZoom((current) => Math.min(1.35, current + 0.1))}>＋ Zoom</button>
                  <button type="button" onClick={() => setSceneZoom((current) => Math.max(0.75, current - 0.1))}>－</button>
                </div>
              </div>

              <div className="reference-canvas-wrap" onWheel={(event) => setSceneZoom((current) => Math.max(0.75, Math.min(1.35, current + (event.deltaY < 0 ? 0.05 : -0.05))))} onPointerDown={startSceneDrag} onPointerMove={moveSceneDrag} onPointerUp={stopSceneDrag} onPointerCancel={stopSceneDrag}>
                <div className="reference-canvas-overlay">
                  <div className="reference-lesson-title">Concepto activo <b>{liveTopic}</b></div>
                  <div className="reference-formula-panel">
                    <div className="reference-formula-label">Acción del agente</div>
                    <div className="reference-formula">{activeAgentComponent?.component_type === "formula" ? activeAgentComponent.payload.text || activeAgentComponent.payload.label || liveAction : liveAction}</div>
                  </div>
                </div>

                <div className="reference-3d-scene" aria-label="Tablero 3D interactivo" style={{ transform: `scale(${sceneZoom}) rotateX(${sceneRotation.x}deg) rotateY(${sceneRotation.y}deg)` }}>
                  {visibleAgentComponent?.component_type === "object3d" ? (
                    <div className={`reference-3d-shape ${visibleAgentComponent.payload.shape === "sphere" ? "sphere" : visibleAgentComponent.payload.shape === "triangle" ? "cube" : "prism"}`} style={{ backgroundColor: visibleAgentComponent.payload.color }} title={visibleAgentComponent.payload.label || "Objeto generado por el agente"} />
                  ) : visibleAgentComponent?.component_type === "formula" ? (
                    <div className="reference-agent-board-content formula">{visibleAgentComponent.payload.text || visibleAgentComponent.payload.label}</div>
                  ) : visibleAgentComponent?.component_type === "highlight" ? (
                    <div className="reference-agent-board-content highlight">{visibleAgentComponent.payload.text || visibleAgentComponent.payload.label}</div>
                  ) : <div className="reference-agent-board-empty">Esperando una propuesta visual del compilador 3D.</div>}
                </div>

                <div className="reference-exercise-panel">
                  <div className="reference-exercise-label">Estado del render <span className="reference-valid-tag">{liveComponent}</span></div>
                  <div className="reference-exercise-row">{activeAgentComponent?.component_type === "highlight" ? activeAgentComponent.payload.text || activeAgentComponent.payload.label || "Concepto destacado por el agente." : latestAgentResult ? "El pipeline respondió para esta sala." : "Envía una instrucción para generar una propuesta."}</div>
                  <div className="reference-exercise-steps">{latestAgentResult?.core_pipeline_error ? <strong>{latestAgentResult.core_pipeline_error}</strong> : activeAgentComponent ? "Propuesta lista para publicar en la sala." : "No hay contenido visual publicado todavía."}</div>
                  {activeAgentComponent && latestAgentResult?.stream_id && (
                    <button type="button" onClick={() => void publishAgentComponentToBoard()} disabled={publishedAgentResultIds.has(latestAgentResult.stream_id)}>
                      {publishedAgentResultIds.has(latestAgentResult.stream_id) ? "Publicado en pizarra" : "Publicar en pizarra"}
                    </button>
                  )}
                </div>

                <div className="reference-tools">
                  <span>▶ Video: cálculo de volumen</span>
                  <span>▦ Tabla: área superficial</span>
                </div>

                <div className="reference-drag-hint">arrastra para rotar · rueda para zoom</div>
              </div>

              <div className="reference-bottom-strip">
                <div className="reference-strip-group">
                  <span className="reference-strip-label">Velocidad pipeline</span>
                  <div className="reference-speed-group">
                    <span>0.5x</span>
                    <span className="active">1x</span>
                    <span>1.6x</span>
                    <span>2.5x</span>
                  </div>
                </div>
                <div className="reference-strip-group">
                  <span className="reference-strip-label">Filtro</span>
                  <div className="reference-chip-group">
                    <span className="active">Todos</span>
                    <span>Poliedros</span>
                    <span>Fórmulas</span>
                    <span>Clave</span>
                  </div>
                </div>
                <div className="reference-history">
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Fragmento</th>
                        <th>Tema</th>
                        <th>Decisión</th>
                        <th>Prioridad</th>
                      </tr>
                    </thead>
                    <tbody>{agentResults.slice(0, 3).map((result, index) => {
                      const pipeline = result.core_pipeline as { semantic_chunk?: { text?: string; topic?: string }; decision?: { action?: string; priority?: string } } | null;
                      return <tr key={result.stream_id ?? index}><td>{index + 1}</td><td>{pipeline?.semantic_chunk?.text?.slice(0, 28) || "Evento procesado"}</td><td>{pipeline?.semantic_chunk?.topic || "—"}</td><td>{pipeline?.decision?.action || "—"}</td><td>{pipeline?.decision?.priority || "—"}</td></tr>;
                    })}</tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="panel portal-panel" aria-labelledby="portal-heading">
          <span className="eyebrow">PORTAL {portalRole.toUpperCase()}</span>
          <h2 id="portal-heading">
            {portalRole === "student"
              ? "Mi espacio académico"
              : portalRole === "teacher"
                ? "Gestión de mi curso"
                : portalRole === "guardian"
                  ? "Seguimiento familiar"
                  : "Operación institucional"}
          </h2>

          {portalRole === "admin" && (
            <>
              <p className="portal-boundary">Vista ejecutiva del tenant con indicadores de admisiones, finanzas y control académico para la operación diaria.</p>
              <div className="catalog-grid" aria-label="Visión ejecutiva del admin">
                <article className="catalog-card">
                  <span className="catalog-kicker">ADMISIONES</span>
                  <strong>{applications.length}</strong>
                  <small>{applications.filter((item) => item.status === "approved").length} aprobadas</small>
                </article>
                <article className="catalog-card">
                  <span className="catalog-kicker">COBRANZA</span>
                  <strong>{(invoices.filter((item) => item.status === "paid").reduce((sum, item) => sum + item.amount_cents, 0) / 100).toLocaleString("es-PE", { style: "currency", currency: "USD" })}</strong>
                  <small>{invoices.filter((item) => item.status === "paid").length} facturas liquidadas</small>
                </article>
                <article className="catalog-card">
                  <span className="catalog-kicker">PROMEDIO</span>
                  <strong>{summary ? summary.average_grade.toFixed(1) : "0.0"}</strong>
                  <small>Rendimiento global del tenant</small>
                </article>
              </div>
            </>
          )}

          {portalRole === "student" && (
            <>
              <p className="portal-boundary">Tus cursos activos y la carga académica de la sesión actual aparecen con aislamiento por tenant.</p>
              <div className="course-list">
                {courses.length === 0 ? (
                  <p className="empty-state">Sin cursos activos para este estudiante.</p>
                ) : (
                  courses.map((course) => (
                    <div className="course-row" key={course.id}>
                      <span className="course-code">{course.code}</span>
                      <strong>{course.name}</strong>
                      <span className="course-status">Activo</span>
                    </div>
                  ))
                )}
              </div>
            </>
          )}

          {portalRole === "teacher" && (
            <>
              <p className="portal-boundary">Cursos asignados y calificaciones visibles solo para este docente dentro del tenant actual.</p>
              <div className="course-list">
                {teacherAssignedCourses.length === 0 ? (
                  <p className="empty-state">Sin cursos asignados.</p>
                ) : (
                  teacherAssignedCourses.map((course) => (
                    <div className="course-row" key={course.id}>
                      <span className="course-code">{course.code}</span>
                      <strong>{course.name}</strong>
                      <span className="course-status">{(teacherCourseGrades[course.id] ?? []).length} notas</span>
                    </div>
                  ))
                )}
              </div>
            </>
          )}

          {portalRole === "guardian" && (
            <>
              <p className="portal-boundary">Estudiantes vinculados y calificaciones autorizadas para seguimiento familiar por tenant.</p>
              <div className="course-list">
                {guardianStudents.length === 0 ? (
                  <p className="empty-state">Sin estudiantes vinculados.</p>
                ) : (
                  guardianStudents.map((student) => (
                    <div className="course-row" key={student.id}>
                      <strong>{student.first_name} {student.last_name}</strong>
                      <span className="course-status">{(guardianStudentGrades[student.id] ?? []).length} notas</span>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}
