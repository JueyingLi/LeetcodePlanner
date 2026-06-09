from datetime import datetime

from pydantic import BaseModel


class SubtopicVariantSummary(BaseModel):
    id: int
    name: str
    slug: str | None = None


class SubtopicCreate(BaseModel):
    name: str
    category: str
    parent_id: int | None = None
    description: str | None = None
    when_to_use: str | None = None
    key_signals: str | None = None
    signals: list[str] | None = None
    variants: str | None = None
    implementation_keys: str | None = None
    common_pitfalls: str | None = None
    core_code: str | None = None
    breakdown: str | None = None
    mental_model: str | None = None
    recall_tasks: list[str] | None = None


class SubtopicUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    parent_id: int | None = None
    description: str | None = None
    when_to_use: str | None = None
    key_signals: str | None = None
    signals: list[str] | None = None
    variants: str | None = None
    implementation_keys: str | None = None
    common_pitfalls: str | None = None
    core_code: str | None = None
    breakdown: str | None = None
    mental_model: str | None = None
    recall_tasks: list[str] | None = None


class SubtopicResponse(BaseModel):
    id: int
    name: str
    slug: str | None = None
    category: str
    parent_id: int | None = None
    parent_name: str | None = None
    description: str | None
    when_to_use: str | None
    key_signals: str | None
    signals: list[str] | None = None
    variants: str | None
    implementation_keys: str | None
    common_pitfalls: str | None
    core_code: str | None = None
    breakdown: str | None = None
    mental_model: str | None = None
    recall_tasks: list[str] | None = None
    related_question_ids: list[int] | None = None
    comparison_same: str | None = None
    comparison_different: str | None = None
    comparison_when: str | None = None
    comparison_code: str | None = None
    variant_children: list[SubtopicVariantSummary] | None = None
    question_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerateVariantRequest(BaseModel):
    variant_name: str


class SubtopicSuggestion(BaseModel):
    name: str
    category: str
    reason: str
