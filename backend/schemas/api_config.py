from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    provider: str
    api_key: str
    model: str | None = None
    is_active: bool = True


class ApiKeyResponse(BaseModel):
    provider: str
    model: str
    is_active: bool
    api_key_masked: str

    model_config = {"from_attributes": True}


class ApiKeyTestRequest(BaseModel):
    provider: str
    api_key: str | None = None


class ApiKeyTestResponse(BaseModel):
    success: bool
    message: str


class InterviewDateUpdate(BaseModel):
    date: str


class StudyPreferenceResponse(BaseModel):
    review_count: int
    template_count: int
    google_count: int
    hard_count: int
    pattern_count: int
    daily_refresh_hour: int
    timezone_offset: int


class StudyPreferenceUpdate(BaseModel):
    review_count: int | None = None
    template_count: int | None = None
    google_count: int | None = None
    hard_count: int | None = None
    pattern_count: int | None = None
    daily_refresh_hour: int | None = None
    timezone_offset: int | None = None
