"""Rewrite older Drill Recall review quizzes so prompts include useful context.

Also repairs or removes older generic prompts such as "what if initialized incorrectly?"
that do not teach a concrete pattern invariant.

Usage:
    uv run python -m backend.scripts.contextualize_drill_recall_quizzes

The script uses the configured DATABASE_URL from .env.
"""

import asyncio

from sqlalchemy import select

from backend.database import async_session
from backend.models.review_quiz import ReviewQuizFormat, ReviewQuizItem
from backend.services.review_quiz_service import _contextualize_existing_drill_recall


async def main() -> None:
    async with async_session() as db:
        user_ids = list((await db.execute(
            select(ReviewQuizItem.user_id)
            .where(ReviewQuizItem.quiz_format == ReviewQuizFormat.DRILL_RECALL)
            .distinct()
        )).scalars().all())

        total = 0
        for user_id in user_ids:
            total += await _contextualize_existing_drill_recall(db, user_id)

        await db.commit()
        print(f"Updated {total} Drill Recall review quiz item(s).")


if __name__ == "__main__":
    asyncio.run(main())
