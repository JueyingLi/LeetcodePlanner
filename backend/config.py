from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'leetcode_planner.db'}"
    fernet_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o"
    # Default interview date used as a fallback when a user has not set their own.
    interview_date: str = "2026-06-23T10:00"
    daily_question_limit: int = 15
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    leetcode_cookie: str = ""
    leetcode_csrf: str = ""

    # Supabase auth
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_aud: str = "authenticated"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
