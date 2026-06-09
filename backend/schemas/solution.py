from datetime import datetime

from pydantic import BaseModel, Field


class EdgeCase(BaseModel):
    case: str
    reasoning: str
    how_handled: str = ""


class SolutionCreate(BaseModel):
    approach_name: str
    initial_observation: str
    approach_reasoning: str
    step_by_step: str
    edge_cases: list[EdgeCase] = Field(default_factory=list)
    time_complexity: str
    space_complexity: str
    code: str
    fill_in_code: str = ""
    is_optimal: bool = False
    sort_order: int = 1


class SolutionResponse(BaseModel):
    id: int
    question_id: int
    approach_name: str
    initial_observation: str
    approach_reasoning: str
    step_by_step: str
    edge_cases: list[EdgeCase]
    time_complexity: str
    space_complexity: str
    code: str
    fill_in_code: str
    is_optimal: bool
    sort_order: int
    llm_provider: str | None
    llm_model: str | None
    generated_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SolutionGenerateRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
