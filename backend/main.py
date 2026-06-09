import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.auth import get_current_user
from backend.config import settings
from backend.database import Base, async_session, engine
from backend.models import attempt, code_mistake, glossary, pattern_clarification, study_plan as study_plan_models, subtopic, user  # noqa: F401 — register models
from backend.routers import attempts, code_mistakes, glossary as glossary_router, import_questions, pattern_drill, questions, quiz, review_quiz, scheduler, settings as settings_router, solutions, study_plan, subtopics


def _migrate_schema(conn):
    from sqlalchemy import text, inspect
    import json
    inspector = inspect(conn)

    if "subtopic_knowledge" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("subtopic_knowledge")}
        for col in ("variants", "implementation_keys", "common_pitfalls", "slug",
                    "core_code", "breakdown", "mental_model", "signals",
                    "recall_tasks", "related_question_ids"):
            if col not in existing:
                if col in ("signals", "recall_tasks", "related_question_ids"):
                    conn.execute(text(f"ALTER TABLE subtopic_knowledge ADD COLUMN {col} JSON"))
                elif col == "slug":
                    conn.execute(text(f"ALTER TABLE subtopic_knowledge ADD COLUMN {col} VARCHAR(80)"))
                else:
                    conn.execute(text(f"ALTER TABLE subtopic_knowledge ADD COLUMN {col} TEXT"))

    if "study_plan_items" in inspector.get_table_names():
        spi_cols = {c["name"] for c in inspector.get_columns("study_plan_items")}
        if "subtopic_id" not in spi_cols:
            conn.execute(text("ALTER TABLE study_plan_items ADD COLUMN subtopic_id INTEGER REFERENCES subtopic_knowledge(id)"))

    if "solutions" in inspector.get_table_names():
        sol_cols = {c["name"] for c in inspector.get_columns("solutions")}
        if "fill_in_code" not in sol_cols:
            conn.execute(text("ALTER TABLE solutions ADD COLUMN fill_in_code TEXT NOT NULL DEFAULT ''"))
        if "pattern_analysis" not in sol_cols:
            conn.execute(text("ALTER TABLE solutions ADD COLUMN pattern_analysis TEXT"))

    if "user_study_preferences" in inspector.get_table_names():
        pref_cols = {c["name"] for c in inspector.get_columns("user_study_preferences")}
        if "daily_refresh_hour" not in pref_cols:
            conn.execute(text("ALTER TABLE user_study_preferences ADD COLUMN daily_refresh_hour INTEGER NOT NULL DEFAULT 5"))
        if "timezone_offset" not in pref_cols:
            conn.execute(text("ALTER TABLE user_study_preferences ADD COLUMN timezone_offset INTEGER NOT NULL DEFAULT 0"))

    if "questions" in inspector.get_table_names():
        q_cols = {c["name"] for c in inspector.get_columns("questions")}
        if "topic" in q_cols and "topics" not in q_cols:
            conn.execute(text("ALTER TABLE questions ADD COLUMN topics TEXT"))
            rows = conn.execute(text("SELECT id, topic FROM questions")).fetchall()
            for row in rows:
                topics_json = json.dumps([row[1]] if row[1] else [])
                conn.execute(text("UPDATE questions SET topics = :t WHERE id = :id"), {"t": topics_json, "id": row[0]})


def _migrate_schema_pg(conn):
    """Additive column patches for Postgres."""
    from sqlalchemy import text
    conn.execute(text("ALTER TABLE solutions ADD COLUMN IF NOT EXISTS fill_in_code TEXT NOT NULL DEFAULT ''"))
    conn.execute(text("ALTER TABLE user_study_preferences ADD COLUMN IF NOT EXISTS daily_refresh_hour INTEGER NOT NULL DEFAULT 5"))
    conn.execute(text("ALTER TABLE user_study_preferences ADD COLUMN IF NOT EXISTS timezone_offset INTEGER NOT NULL DEFAULT 0"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS slug VARCHAR(80)"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS core_code TEXT"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS breakdown TEXT"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS mental_model TEXT"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS signals JSON"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS recall_tasks JSON"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS related_question_ids JSON"))
    conn.execute(text("ALTER TABLE study_plan_items ADD COLUMN IF NOT EXISTS subtopic_id INTEGER REFERENCES subtopic_knowledge(id)"))
    conn.execute(text("ALTER TABLE solutions ADD COLUMN IF NOT EXISTS pattern_analysis JSON"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES subtopic_knowledge(id)"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS comparison_same TEXT"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS comparison_different TEXT"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS comparison_when TEXT"))
    conn.execute(text("ALTER TABLE subtopic_knowledge ADD COLUMN IF NOT EXISTS comparison_code TEXT"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_subtopic_knowledge_parent_id ON subtopic_knowledge(parent_id)"))

    # Normalized join tables
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS question_subtopics (
            id SERIAL PRIMARY KEY,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            subtopic_id INTEGER NOT NULL REFERENCES subtopic_knowledge(id) ON DELETE CASCADE
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_subtopics_question_id ON question_subtopics(question_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_subtopics_subtopic_id ON question_subtopics(subtopic_id)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS question_topics (
            id SERIAL PRIMARY KEY,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            topic_name VARCHAR(100) NOT NULL
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_topics_question_id ON question_topics(question_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_topics_topic_name ON question_topics(topic_name)"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS question_source_links (
            id SERIAL PRIMARY KEY,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            source_post_id INTEGER REFERENCES question_source_posts(id) ON DELETE SET NULL,
            source_name VARCHAR(100) NOT NULL,
            source_type VARCHAR(50) NOT NULL DEFAULT 'list',
            score FLOAT NOT NULL DEFAULT 0.0
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_source_links_question_id ON question_source_links(question_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_question_source_links_source_post_id ON question_source_links(source_post_id)"))


async def _sync_taxonomy(db):
    """Insert any subtopics from TAXONOMY that don't exist in the database yet."""
    from backend.models.subtopic import SubtopicKnowledge
    from backend.services import subtopic_service
    from backend.taxonomy import TAXONOMY

    existing = set(n.lower() for n in await subtopic_service.get_all_subtopic_names(db))
    for entry in TAXONOMY:
        for st_data in entry["subtopics"]:
            if st_data["name"].lower() not in existing:
                db.add(SubtopicKnowledge(
                    name=st_data["name"],
                    category=entry["topic"],
                    description=st_data.get("description"),
                    when_to_use=st_data.get("when_to_use"),
                    key_signals=st_data.get("key_signals"),
                    variants=st_data.get("variants"),
                    implementation_keys=st_data.get("implementation_keys"),
                    common_pitfalls=st_data.get("common_pitfalls"),
                ))
    await db.commit()


async def _sync_question_links(db):
    """Populate join tables from JSON arrays if they're empty (first-run migration)."""
    from sqlalchemy import func, select
    from backend.models.question_links import QuestionSubtopic, QuestionTopic
    sub_count = (await db.execute(select(func.count(QuestionSubtopic.id)))).scalar() or 0
    topic_count = (await db.execute(select(func.count(QuestionTopic.id)))).scalar() or 0
    if sub_count > 0 and topic_count > 0:
        return
    from backend.services.question_link_service import migrate_all_json_to_links
    migrated = await migrate_all_json_to_links(db)
    await db.commit()
    if migrated:
        import logging
        logging.getLogger(__name__).info("Migrated %d questions to normalized link tables", migrated)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all does not ALTER existing tables, so additive columns are patched
        # in per-dialect (SQLite uses SQLite-specific DDL; Postgres uses IF NOT EXISTS).
        if settings.database_url.startswith("sqlite"):
            await conn.run_sync(_migrate_schema)
        else:
            await conn.run_sync(_migrate_schema_pg)
    async with async_session() as db:
        await _sync_taxonomy(db)
        await _sync_question_links(db)
    yield
    await engine.dispose()


app = FastAPI(
    title="LeetCode Crasher",
    description="Duolingo-style LeetCode preparation tool",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Auth uses bearer tokens (not cookies), so we don't need credentialed CORS.
    # Restrict to the configured origins instead of a wildcard.
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(questions.router)
app.include_router(solutions.router)
app.include_router(solutions.batch_router)
app.include_router(quiz.router)
app.include_router(review_quiz.router)
app.include_router(scheduler.router)
app.include_router(settings_router.router)
app.include_router(import_questions.router)
app.include_router(subtopics.router)
app.include_router(attempts.router)
app.include_router(study_plan.router)
app.include_router(study_plan.template_router)
app.include_router(pattern_drill.router)
app.include_router(glossary_router.router)
app.include_router(code_mistakes.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {exc}",
            "traceback": "".join(tb[-3:]),
        },
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/me")
async def me(current=Depends(get_current_user)):
    return {
        "id": current.id,
        "email": current.email,
        "interview_date": current.interview_date,
    }


frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
