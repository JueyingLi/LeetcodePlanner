"""One-time migration: copy data from the old single-user SQLite database
into the new (Supabase Postgres) database.

Shared content (questions, solutions, subtopic knowledge) is always copied.
Per-user rows (progress, quiz attempts, solve attempts, API keys) are copied
only when --owner-user-id is given, and are attached to that user.

Usage:
    # Point the app at the target DB (Supabase) via DATABASE_URL, then:
    DATABASE_URL='postgresql+asyncpg://...' \
        python -m backend.scripts.migrate_sqlite \
        --source data/leetcode_planner.db \
        --owner-user-id <your-supabase-user-uuid>

The owner UUID is the `sub` of your Supabase user — sign in once, then read it
from GET /api/me (the `id` field).
"""

import argparse
import asyncio
import json
import sqlite3

from sqlalchemy import select

from backend.config import settings
from backend.database import async_session, engine
from backend.models.api_config import ApiConfig
from backend.models.attempt import UserAttempt
from backend.models.progress import UserProgress
from backend.models.question import Difficulty, Question, Status
from backend.models.quiz import QuizAttempt, QuizFocus, QuizType
from backend.models.solution import Solution
from backend.models.subtopic import SubtopicKnowledge
from backend.models.user import User


def _open_source(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _jload(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _enum(enum_cls, raw):
    """Old SQLite stored enums by NAME (e.g. 'MEDIUM'); newer code uses values
    (e.g. 'Medium'). Accept either."""
    try:
        return enum_cls(raw)
    except ValueError:
        return enum_cls[raw]


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


async def _reset_sequences(session, tables: list[str]) -> None:
    """After inserting explicit integer PKs on Postgres, advance the sequence."""
    if not settings.database_url.startswith("postgresql"):
        return
    from sqlalchemy import text

    for table in tables:
        await session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )
        )


async def migrate(source: str, owner_user_id: str | None) -> None:
    src = _open_source(source)

    async with async_session() as session:
        # --- Shared content: questions ---
        q_cols = _cols(src, "questions")
        rows = src.execute("SELECT * FROM questions").fetchall()
        for r in rows:
            exists = await session.get(Question, r["id"])
            if exists:
                continue
            topics = _jload(r["topics"], []) if "topics" in q_cols else (
                [r["topic"]] if "topic" in q_cols and r["topic"] else []
            )
            session.add(Question(
                id=r["id"],
                number=r["number"],
                title=r["title"],
                difficulty=_enum(Difficulty, r["difficulty"]),
                topics=topics,
                subtopics=_jload(r["subtopics"], []),
                frequency=r["frequency"] or 0.0,
                sources=_jload(r["sources"], []),
                url=r["url"],
                description=r["description"] if "description" in q_cols else None,
                examples=_jload(r["examples"], None) if "examples" in q_cols else None,
                notes=r["notes"],
            ))
        await session.commit()
        print(f"questions: {len(rows)} processed")

        # --- Shared content: solutions ---
        rows = src.execute("SELECT * FROM solutions").fetchall()
        for r in rows:
            if await session.get(Solution, r["id"]):
                continue
            session.add(Solution(
                id=r["id"],
                question_id=r["question_id"],
                approach_name=r["approach_name"],
                description_reminder=r["description_reminder"],
                initial_observation=r["initial_observation"],
                approach_reasoning=r["approach_reasoning"],
                step_by_step=r["step_by_step"],
                edge_cases=_jload(r["edge_cases"], []),
                time_complexity=r["time_complexity"],
                space_complexity=r["space_complexity"],
                code=r["code"],
                is_optimal=bool(r["is_optimal"]),
                sort_order=r["sort_order"],
                llm_provider=r["llm_provider"],
                llm_model=r["llm_model"],
            ))
        await session.commit()
        print(f"solutions: {len(rows)} processed")

        # --- Shared content: subtopic knowledge ---
        if "subtopic_knowledge" in {t[0] for t in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}:
            st_cols = _cols(src, "subtopic_knowledge")
            rows = src.execute("SELECT * FROM subtopic_knowledge").fetchall()
            for r in rows:
                if await session.get(SubtopicKnowledge, r["id"]):
                    continue
                session.add(SubtopicKnowledge(
                    id=r["id"],
                    name=r["name"],
                    category=r["category"],
                    description=r["description"],
                    when_to_use=r["when_to_use"],
                    key_signals=r["key_signals"],
                    variants=r["variants"] if "variants" in st_cols else None,
                    implementation_keys=r["implementation_keys"] if "implementation_keys" in st_cols else None,
                    common_pitfalls=r["common_pitfalls"] if "common_pitfalls" in st_cols else None,
                ))
            await session.commit()
            print(f"subtopic_knowledge: {len(rows)} processed")

        await _reset_sequences(session, ["questions", "solutions", "subtopic_knowledge"])
        await session.commit()

        if not owner_user_id:
            print("No --owner-user-id given; skipped per-user tables.")
            src.close()
            return

        # Ensure the owner user exists locally.
        owner = await session.get(User, owner_user_id)
        if not owner:
            session.add(User(id=owner_user_id, interview_date=settings.interview_date))
            await session.commit()
            print(f"created user row for {owner_user_id}")

        # --- Per-user: progress ---
        rows = src.execute("SELECT * FROM user_progress").fetchall()
        for r in rows:
            dup = await session.execute(
                select(UserProgress).where(
                    UserProgress.user_id == owner_user_id,
                    UserProgress.question_id == r["question_id"],
                )
            )
            if dup.scalar_one_or_none():
                continue
            session.add(UserProgress(
                user_id=owner_user_id,
                question_id=r["question_id"],
                ease_factor=r["ease_factor"],
                interval=r["interval"],
                repetitions=r["repetitions"],
                last_reviewed=r["last_reviewed"],
                next_review=r["next_review"],
                quality_history=_jload(r["quality_history"], []),
                quiz_correct_count=r["quiz_correct_count"],
                quiz_total_count=r["quiz_total_count"],
            ))
        await session.commit()
        print(f"user_progress: {len(rows)} processed")

        # --- Per-user: study status (was a global column on questions) ---
        # Only persist non-TODO statuses; a missing row implies TODO.
        qrows = src.execute("SELECT id, status FROM questions").fetchall()
        status_set = 0
        for qr in qrows:
            st = _enum(Status, qr["status"])
            if st == Status.TODO:
                continue
            res = await session.execute(
                select(UserProgress).where(
                    UserProgress.user_id == owner_user_id,
                    UserProgress.question_id == qr["id"],
                )
            )
            prog = res.scalar_one_or_none()
            if prog is None:
                session.add(UserProgress(
                    user_id=owner_user_id, question_id=qr["id"], status=st
                ))
            else:
                prog.status = st
            status_set += 1
        await session.commit()
        print(f"question status: {status_set} non-TODO migrated")

        # --- Per-user: quiz attempts ---
        rows = src.execute("SELECT * FROM quiz_attempts").fetchall()
        for r in rows:
            session.add(QuizAttempt(
                user_id=owner_user_id,
                question_id=r["question_id"],
                quiz_type=_enum(QuizType, r["quiz_type"]),
                quiz_focus=_enum(QuizFocus, r["quiz_focus"]),
                quiz_data=_jload(r["quiz_data"], {}),
                user_answer=r["user_answer"],
                correct_answer=r["correct_answer"],
                is_correct=None if r["is_correct"] is None else bool(r["is_correct"]),
                time_spent_seconds=r["time_spent_seconds"],
            ))
        await session.commit()
        print(f"quiz_attempts: {len(rows)} processed")

        # --- Per-user: solve attempts ---
        rows = src.execute("SELECT * FROM user_attempts").fetchall()
        for r in rows:
            session.add(UserAttempt(
                user_id=owner_user_id,
                question_id=r["question_id"],
                observation=r["observation"],
                approach=r["approach"],
                code=r["code"],
                time_complexity=r["time_complexity"],
                space_complexity=r["space_complexity"],
                ai_feedback=_jload(r["ai_feedback"], None),
            ))
        await session.commit()
        print(f"user_attempts: {len(rows)} processed")

        # --- Per-user: API keys ---
        rows = src.execute("SELECT * FROM api_config").fetchall()
        for r in rows:
            dup = await session.execute(
                select(ApiConfig).where(
                    ApiConfig.user_id == owner_user_id,
                    ApiConfig.provider == r["provider"],
                )
            )
            if dup.scalar_one_or_none():
                continue
            session.add(ApiConfig(
                user_id=owner_user_id,
                provider=r["provider"],
                api_key_encrypted=r["api_key_encrypted"],
                model=r["model"],
                is_active=bool(r["is_active"]),
            ))
        await session.commit()
        print(f"api_config: {len(rows)} processed")

    src.close()
    await engine.dispose()
    print("Migration complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate old SQLite data to the configured DB")
    parser.add_argument("--source", default="data/leetcode_planner.db", help="Path to the old SQLite file")
    parser.add_argument("--owner-user-id", default=None, help="Supabase user UUID to attach per-user data to")
    args = parser.parse_args()

    if settings.database_url.startswith("sqlite"):
        print("WARNING: target DATABASE_URL is SQLite. Set it to your Supabase Postgres URL first.")
    asyncio.run(migrate(args.source, args.owner_user_id))


if __name__ == "__main__":
    main()
