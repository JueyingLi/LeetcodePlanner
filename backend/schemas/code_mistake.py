from datetime import datetime

from pydantic import BaseModel


class CodeMistakeCreate(BaseModel):
    subtopic_id: int | None = None
    subtopic_name: str
    correct_code: str
    user_code: str
    context_line: str | None = None


class CodeMistakeResponse(BaseModel):
    id: int
    subtopic_id: int | None
    subtopic_name: str
    correct_code: str
    user_code: str
    context_line: str | None
    analysis: str | None
    weakness_tag: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
