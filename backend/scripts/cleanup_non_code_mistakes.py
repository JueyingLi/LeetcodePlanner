import asyncio

from sqlalchemy import delete, select

from backend.database import async_session
from backend.models.code_mistake import CodeMistake
from backend.models.review_quiz import ReviewQuizFormat, ReviewQuizItem, ReviewQuizSourceType
from backend.services.code_snippet_filter import is_actual_code


async def main() -> None:
    async with async_session() as db:
        mistakes = (await db.execute(
            select(CodeMistake.id, CodeMistake.correct_code)
        )).all()
        bad_mistake_ids = [
            mistake_id for mistake_id, correct_code in mistakes
            if not is_actual_code(correct_code)
        ]

        repair_items = (await db.execute(
            select(ReviewQuizItem.id, ReviewQuizItem.source_id, ReviewQuizItem.correct_answer)
            .where(ReviewQuizItem.quiz_format == ReviewQuizFormat.CODE_REPAIR)
        )).all()
        bad_mistake_id_set = set(bad_mistake_ids)
        bad_item_ids = [
            item_id
            for item_id, source_id, correct_answer in repair_items
            if source_id in bad_mistake_id_set or not is_actual_code(correct_answer)
        ]

        if bad_item_ids:
            await db.execute(
                delete(ReviewQuizItem).where(ReviewQuizItem.id.in_(bad_item_ids))
            )
        if bad_mistake_ids:
            await db.execute(
                delete(ReviewQuizItem).where(
                    ReviewQuizItem.source_type == ReviewQuizSourceType.CODE_MISTAKE,
                    ReviewQuizItem.source_id.in_(bad_mistake_ids),
                )
            )
            await db.execute(
                delete(CodeMistake).where(CodeMistake.id.in_(bad_mistake_ids))
            )

        await db.commit()
        print(f"Deleted {len(bad_mistake_ids)} non-code code_mistakes")
        print(f"Deleted {len(bad_item_ids)} non-code code_repair review_quiz_items")


if __name__ == "__main__":
    asyncio.run(main())
