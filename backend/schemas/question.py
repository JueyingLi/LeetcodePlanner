from datetime import datetime

from pydantic import BaseModel, Field

from backend.models.question import Difficulty, Status


class SourceTag(BaseModel):
    name: str
    type: str = "list"


class ExampleItem(BaseModel):
    input: str
    output: str
    explanation: str = ""


class CodeStep(BaseModel):
    code: str = Field(description="The critical 1-5 lines of code")
    explanation: str = Field(description="What this code does and why it's necessary")


class ApproachStep(BaseModel):
    label: str = Field(description="Canonical name of the data structure or algorithm (e.g. 'Min-Heap', 'Dijkstra', 'Union-Find')")
    category: str = Field(description="One of: data_structure | algorithm | optimization")
    why: str = Field(description="Why this technique fits given the data characteristics — what breaks without it")
    code_steps: list[CodeStep] = Field(default_factory=list, description="The critical code lines from the solution that implement this technique")


class DrillQuestion(BaseModel):
    question: str = Field(description="Specific, targeted question that tests understanding of this problem")
    answer: str = Field(description="Detailed correct answer that teaches — not just names a technique but explains WHY")
    wrong_options: list[str] = Field(default_factory=list, description="3 plausible wrong answers for quiz mode")
    approach_label: str = Field(default="", description="Category label: one of 'observation', 'data structure', 'algorithm', 'approach', or 'optimization'")


class PatternAnalysis(BaseModel):
    scenario: str = Field(
        default="",
        description="Brief problem scenario in 1-2 sentences — what the problem is about without giving away the solution",
    )
    example: str = Field(
        default="",
        description="One input/output example. Each on its own line: 'Input: ...\\nOutput: ...\\nExplanation: ...'",
    )
    data_characteristics: str = Field(
        default="",
        description="What's special about this input data — shape, properties, constraints that point to a technique",
    )
    goal: str = Field(
        default="",
        description="What to compute or return, stated concisely",
    )
    constraint_signals: list[str] = Field(
        default_factory=list,
        description="Key constraints or phrases that signal which technique to use (e.g. 'non-negative weights → Dijkstra')",
    )
    approaches: list[ApproachStep] = Field(
        default_factory=list,
        description="Ordered list of techniques used: data structures first, then algorithms, then optimizations",
    )
    questions: list[DrillQuestion] = Field(
        default_factory=list,
        description="Guided drill questions following the mind-map flow: observation → technique → improvement",
    )


class QuestionCreate(BaseModel):
    number: int | None = None
    title: str
    difficulty: Difficulty
    topics: list[str] = Field(default_factory=list)
    subtopics: list[str] = Field(default_factory=list)
    frequency: float = 0.0
    sources: list[SourceTag] = Field(default_factory=list)
    url: str | None = None
    description: str | None = None
    examples: list[ExampleItem] | None = None
    notes: str | None = None


class QuestionUpdate(BaseModel):
    number: int | None = None
    title: str | None = None
    difficulty: Difficulty | None = None
    topics: list[str] | None = None
    subtopics: list[str] | None = None
    frequency: float | None = None
    sources: list[SourceTag] | None = None
    url: str | None = None
    description: str | None = None
    examples: list[ExampleItem] | None = None
    notes: str | None = None


class StatusUpdate(BaseModel):
    status: Status


class QuestionResponse(BaseModel):
    id: int
    number: int | None
    title: str
    difficulty: Difficulty
    topics: list[str]
    subtopics: list[str]
    frequency: float
    sources: list[SourceTag]
    url: str | None
    description: str | None
    examples: list[ExampleItem] | None
    notes: str | None
    status: Status
    created_at: datetime
    updated_at: datetime
    solution_count: int = 0
    has_progress: bool = False

    model_config = {"from_attributes": True}


class QuestionListResponse(BaseModel):
    items: list[QuestionResponse]
    total: int


class QuestionImportRequest(BaseModel):
    text: str
    default_source: str | None = None


class QuestionImportResponse(BaseModel):
    added: int
    updated: int
    skipped: int
    questions: list[QuestionResponse]
