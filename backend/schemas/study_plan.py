from datetime import date, datetime

from pydantic import BaseModel, Field


class TemplateSummaryResponse(BaseModel):
    id: int
    slug: str
    title: str
    topic: str
    subtopic: str | None
    when_to_use: str
    signals: list[str]
    last_reviewed: datetime | None = None
    next_review: datetime | None = None


class TemplateDetailResponse(TemplateSummaryResponse):
    core_code: str
    breakdown: str
    mental_model: str
    variants: str
    pitfalls: str
    recall_tasks: list[str]
    related_question_ids: list[int]


class TemplateReviewRequest(BaseModel):
    quality: int = Field(ge=0, le=5)
    notes: str | None = None


class TemplateReviewResponse(BaseModel):
    template_id: int
    quality_history: list[int]
    last_reviewed: datetime | None
    next_review: datetime | None
    notes: str | None


class StudyPlanItemResponse(BaseModel):
    id: int
    item_type: str
    question_id: int | None
    template_id: int | None
    title: str
    reason: str
    priority: int
    status: str
    pinned: bool
    manual: bool
    estimated_minutes: int
    sort_order: int
    notes: str | None
    metadata: dict = Field(default_factory=dict)
    template: TemplateDetailResponse | None = None


class StudyPlanSessionResponse(BaseModel):
    id: int
    session_type: str
    title: str
    description: str | None
    sort_order: int
    estimated_minutes: int
    items: list[StudyPlanItemResponse]


class StudyPlanResponse(BaseModel):
    id: int
    date: date
    interview_target: str
    status: str
    generated_at: datetime
    updated_at: datetime
    regenerated_count: int
    days_until_interview: int
    hours_until_interview: int
    minutes_until_interview: int
    summary: dict
    markdown_snapshot: str
    sessions: list[StudyPlanSessionResponse]


class StudyPlanItemUpdate(BaseModel):
    status: str | None = None
    pinned: bool | None = None
    notes: str | None = None


class AddPatternDrillsRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=20)


class AddTemplatesRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=10)
    subtopic_id: int | None = None


class SourceImportRequest(BaseModel):
    text: str
    title: str | None = None
    url: str | None = None


class SourceScrapeRequest(BaseModel):
    max_results: int = Field(default=200, ge=1, le=200)
    max_comments: int = Field(default=20, ge=0, le=50)


class SourcePostResponse(BaseModel):
    id: int
    source_type: str
    uuid: str | None
    topic_id: int | None
    slug: str | None
    title: str
    url: str | None
    summary: str | None
    full_text_preview: str | None
    created_at_from_source: str | None
    updated_at_from_source: str | None
    hit_count: int | None
    comment_count: int | None
    score: int
    extracted_questions: list[str]
    imported_at: datetime


class SourceImportResponse(BaseModel):
    posts_added: int
    posts_updated: int
    questions_added: int
    questions_updated: int
    questions_skipped: int
    posts: list[SourcePostResponse] = Field(default_factory=list)
