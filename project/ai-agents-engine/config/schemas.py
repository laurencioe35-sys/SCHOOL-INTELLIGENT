"""
Validación estricta del JSON que producen los agentes antes de que llegue
al frontend. Esto es lo que evita que una alucinación del LLM rompa la
UI: si el JSON no calza con este esquema, se rechaza y no se renderiza.
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class SemanticChunk(BaseModel):
    """Salida del context_agent: un fragmento de lo que dijo el profesor,
    con su clasificación semántica."""
    text: str
    topic: str
    confidence: float = Field(ge=0.0, le=1.0)


class PedagogicalDecision(BaseModel):
    """Salida del pedagogical_agent: qué hacer con ese fragmento."""
    action: Literal["render_3d_object", "render_formula", "highlight_concept", "no_action"]
    reason: str
    priority: Literal["low", "medium", "high"] = "medium"


class UIComponentSchema(BaseModel):
    """Salida del ui_compiler_agent: el JSON final validado que consume
    el frontend para decidir qué pintar en el canvas 3D. Este es el
    'contrato' entre el backend de IA y el frontend inmersivo."""
    component_type: Literal["object3d", "formula", "highlight"]
    payload: dict
    session_id: str

    @field_validator("payload")
    @classmethod
    def payload_not_empty(cls, v):
        if not v:
            raise ValueError("payload no puede estar vacío")
        return v


class AgentPipelineResult(BaseModel):
    semantic_chunk: SemanticChunk
    decision: PedagogicalDecision
    ui_component: Optional[UIComponentSchema] = None


# --- Esquemas de los agentes nuevos (orchestrator/ + agents_v2/) ---------

class GradingResult(BaseModel):
    """Salida del grading_agent: calificación automática de una respuesta
    de alumno contra una rúbrica simple de puntos clave esperados."""
    student_answer: str
    score: float = Field(ge=0.0, le=1.0)
    matched_key_points: list[str] = Field(default_factory=list)
    feedback: str
    needs_teacher_review: bool = False

    @field_validator("feedback")
    @classmethod
    def feedback_not_empty(cls, v):
        if not v.strip():
            raise ValueError("feedback no puede estar vacío")
        return v


class QuizQuestion(BaseModel):
    question: str
    options: list[str] = Field(min_length=2, max_length=5)
    correct_index: int = Field(ge=0)

    @field_validator("correct_index")
    @classmethod
    def index_in_range(cls, v, info):
        options = info.data.get("options")
        if options is not None and v >= len(options):
            raise ValueError("correct_index fuera de rango de options")
        return v


class GeneratedQuiz(BaseModel):
    """Salida del content_generator_agent: mini-quiz derivado del tema
    detectado por el context_agent, para reforzar lo que se acaba de
    explicar en clase."""
    topic: str
    questions: list[QuizQuestion] = Field(min_length=1, max_length=5)
    session_id: str


class AnalyticsSnapshot(BaseModel):
    """Salida del analytics_agent: fotografía acumulada del estado de una
    sesión de clase, leída del blackboard (no vuelve a calcular desde
    cero — agrega sobre lo que ya escribieron los otros agentes)."""
    session_id: str
    chunks_processed: int = 0
    topics_covered: list[str] = Field(default_factory=list)
    action_counts: dict[str, int] = Field(default_factory=dict)
    agent_errors: int = 0
    submissions_graded: int = 0
    submissions_pending_review: int = 0
    dead_letter_count: int = 0


class SolvedExercise(BaseModel):
    """Salida de los agentes de materia (subject_agents/): un ejercicio
    ORIGINAL, generado por LLM (o por el mock determinístico en modo
    prueba), nunca copiado ni extraído de ningún libro con copyright.
    'steps' obliga a que la solución venga desglosada paso a paso, no
    solo la respuesta final."""
    subject: str
    topic: str
    difficulty: Literal["basico", "intermedio", "avanzado"] = "basico"
    statement: str
    steps: list[str] = Field(min_length=1)
    final_answer: str

    @field_validator("statement", "final_answer")
    @classmethod
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("no puede estar vacío")
        return v
