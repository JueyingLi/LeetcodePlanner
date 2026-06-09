from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.subtopic import SubtopicKnowledge
from backend.models.user import User
from backend.routers.questions import _to_response
from backend.schemas.subtopic import GenerateVariantRequest, SubtopicCreate, SubtopicResponse, SubtopicUpdate
from backend.services import subtopic_service

router = APIRouter(prefix="/api/subtopics", tags=["subtopics"])


def _apply_generated_fields(st, desc: dict) -> None:
    st.description = desc.get("description", "")
    st.when_to_use = desc.get("when_to_use", "")
    st.key_signals = desc.get("key_signals", "")
    st.variants = desc.get("variants", "")
    st.implementation_keys = desc.get("implementation_keys", "")
    st.common_pitfalls = desc.get("common_pitfalls", "")
    if desc.get("core_code"):
        st.core_code = desc["core_code"]
    if desc.get("breakdown"):
        st.breakdown = desc["breakdown"]
    if desc.get("mental_model"):
        st.mental_model = desc["mental_model"]
    if desc.get("signals"):
        st.signals = desc["signals"]
    if desc.get("recall_tasks"):
        st.recall_tasks = desc["recall_tasks"]
    if desc.get("comparison_same"):
        st.comparison_same = desc["comparison_same"]
    if desc.get("comparison_different"):
        st.comparison_different = desc["comparison_different"]
    if desc.get("comparison_when"):
        st.comparison_when = desc["comparison_when"]
    if desc.get("comparison_code"):
        st.comparison_code = desc["comparison_code"]


@router.get("", response_model=list[SubtopicResponse])
async def list_subtopics(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await subtopic_service.list_subtopics(db, category)


@router.get("/categories", response_model=list[str])
async def get_categories(db: AsyncSession = Depends(get_db)):
    return await subtopic_service.get_categories(db)


@router.get("/topic-order", response_model=list[str])
async def get_topic_order():
    from backend.taxonomy import TOPIC_ORDER
    return TOPIC_ORDER


@router.get("/names", response_model=list[str])
async def get_subtopic_names(db: AsyncSession = Depends(get_db)):
    return await subtopic_service.get_all_subtopic_names(db)


@router.get("/{subtopic_id}", response_model=SubtopicResponse)
async def get_subtopic(subtopic_id: int, db: AsyncSession = Depends(get_db)):
    st = await subtopic_service.get_subtopic(db, subtopic_id)
    if not st:
        raise HTTPException(status_code=404, detail="Subtopic not found")
    return SubtopicResponse.model_validate(st)


@router.get("/{subtopic_id}/questions")
async def get_subtopic_questions(
    subtopic_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    st = await subtopic_service.get_subtopic(db, subtopic_id)
    if not st:
        raise HTTPException(status_code=404, detail="Subtopic not found")
    questions = await subtopic_service.get_questions_by_subtopic(db, st.name)
    from backend.services import question_service
    status_map = await question_service.get_status_map(db, user.id, [q.id for q in questions])
    return [_to_response(q, status_map.get(q.id, "todo"), q.id in status_map) for q in questions]


@router.get("/{subtopic_id}/variants", response_model=list[SubtopicResponse])
async def get_subtopic_variants(
    subtopic_id: int,
    db: AsyncSession = Depends(get_db),
):
    st = await subtopic_service.get_subtopic(db, subtopic_id)
    if not st:
        raise HTTPException(status_code=404, detail="Subtopic not found")
    variants = []
    for child in (st.children or []):
        from sqlalchemy import func, select as sa_select
        from backend.models.question_links import QuestionSubtopic
        count_result = await db.execute(
            sa_select(func.count(QuestionSubtopic.id))
            .where(QuestionSubtopic.subtopic_id == child.id)
        )
        count = count_result.scalar() or 0
        variants.append(SubtopicResponse.model_validate({
            **subtopic_service._to_dict(child),
            "question_count": count,
        }))
    return variants


@router.post("/{subtopic_id}/generate-variant", response_model=SubtopicResponse)
async def generate_variant(
    subtopic_id: int,
    body: GenerateVariantRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from backend.agents.subtopic_agent import SubtopicAgent

    parent = await subtopic_service.get_subtopic(db, subtopic_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent subtopic not found")

    existing = await subtopic_service.get_subtopic_by_name(db, body.variant_name)
    if existing:
        existing = await subtopic_service.get_subtopic(db, existing.id) or existing
        from sqlalchemy import func, select as sa_select
        from backend.models.question_links import QuestionSubtopic
        count_result = await db.execute(
            sa_select(func.count(QuestionSubtopic.id))
            .where(QuestionSubtopic.subtopic_id == existing.id)
        )
        count = count_result.scalar() or 0
        return SubtopicResponse.model_validate({
            **subtopic_service._to_dict(existing),
            "question_count": count,
        })

    agent = SubtopicAgent()
    try:
        desc = await agent.generate_variant(
            db,
            variant_name=body.variant_name,
            parent_name=parent.name,
            parent_description=parent.description,
            parent_core_code=parent.core_code,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    slug = body.variant_name.lower().replace(" ", "-").replace("/", "-")
    variant = SubtopicKnowledge(
        name=body.variant_name,
        slug=slug,
        category=parent.category,
        parent_id=parent.id,
    )
    _apply_generated_fields(variant, desc)
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    return SubtopicResponse.model_validate({
        **subtopic_service._to_dict(variant),
        "question_count": 0,
    })


@router.post("", response_model=SubtopicResponse, status_code=201)
async def create_subtopic(data: SubtopicCreate, db: AsyncSession = Depends(get_db)):
    existing = await subtopic_service.get_subtopic_by_name(db, data.name)
    if existing:
        raise HTTPException(status_code=409, detail="Subtopic already exists")
    st = await subtopic_service.create_subtopic(db, data)
    return SubtopicResponse.model_validate(st)


@router.put("/{subtopic_id}", response_model=SubtopicResponse)
async def update_subtopic(
    subtopic_id: int, data: SubtopicUpdate, db: AsyncSession = Depends(get_db)
):
    st = await subtopic_service.update_subtopic(db, subtopic_id, data)
    if not st:
        raise HTTPException(status_code=404, detail="Subtopic not found")
    return SubtopicResponse.model_validate(st)


@router.delete("/{subtopic_id}", status_code=204)
async def delete_subtopic(subtopic_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await subtopic_service.delete_subtopic(db, subtopic_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subtopic not found")


@router.post("/generate-descriptions")
async def generate_descriptions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate AI descriptions for subtopics that don't have one."""
    from backend.agents.subtopic_agent import SubtopicAgent

    subtopics = await subtopic_service.list_subtopics(db)
    missing = [s for s in subtopics if not s.get("description")]
    if not missing:
        return {"updated": 0, "message": "All subtopics already have descriptions"}

    agent = SubtopicAgent()
    try:
        descriptions = await agent.generate(db, [s["name"] for s in missing])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    name_to_desc = {}
    for desc in descriptions:
        name_to_desc[desc["name"].lower().strip()] = desc

    updated = 0
    for s in missing:
        desc = name_to_desc.get(s["name"].lower().strip())
        if not desc:
            for key, val in name_to_desc.items():
                if key in s["name"].lower() or s["name"].lower() in key:
                    desc = val
                    break
        if not desc:
            continue
        st = await subtopic_service.get_subtopic(db, s["id"])
        if st:
            _apply_generated_fields(st, desc)
            updated += 1
    await db.commit()
    return {"updated": updated}


@router.post("/{subtopic_id}/regenerate-description", response_model=SubtopicResponse)
async def regenerate_description(
    subtopic_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Regenerate AI learning content for one pattern."""
    from backend.agents.subtopic_agent import SubtopicAgent

    st = await subtopic_service.get_subtopic(db, subtopic_id)
    if not st:
        raise HTTPException(status_code=404, detail="Subtopic not found")

    agent = SubtopicAgent()
    try:
        descriptions = await agent.generate(db, [st.name])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    desc = None
    for item in descriptions:
        if item["name"].lower().strip() == st.name.lower().strip():
            desc = item
            break
    if not desc and descriptions:
        desc = descriptions[0]
    if not desc:
        raise HTTPException(status_code=502, detail="AI generation returned no content")

    _apply_generated_fields(st, desc)
    await db.commit()
    await db.refresh(st)
    return SubtopicResponse.model_validate(st)


@router.post("/{subtopic_id}/find-and-add-questions")
async def find_and_add_questions(
    subtopic_id: int,
    count: int = 3,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search for LeetCode questions matching this pattern, add them with AI solutions."""
    from backend.agents.question_finder_agent import QuestionFinderAgent
    from backend.models.question import Difficulty, Question
    from backend.services import question_service, solution_service
    from backend.taxonomy import SUBTOPIC_TO_TOPIC

    st = await subtopic_service.get_subtopic(db, subtopic_id)
    if not st:
        raise HTTPException(status_code=404, detail="Subtopic not found")

    existing = await subtopic_service.get_questions_by_subtopic(db, st.name)
    exclude_numbers = [q.number for q in existing if q.number]

    agent = QuestionFinderAgent()
    try:
        found = await agent.find_questions(
            db, st.name, st.description, count=max(3, count), exclude_numbers=exclude_numbers
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI question search failed: {e}")

    added = []
    errors = []
    topic = SUBTOPIC_TO_TOPIC.get(st.name.lower(), st.category)

    for fq in found:
        existing_q = await question_service.get_question_by_number(db, fq["number"])
        if existing_q:
            changed = False
            if st.name not in (existing_q.subtopics or []):
                existing_q.subtopics = list(existing_q.subtopics or []) + [st.name]
                changed = True
            if topic and topic not in (existing_q.topics or []):
                existing_q.topics = list(existing_q.topics or []) + [topic]
                changed = True
            if changed:
                await db.commit()
                await db.refresh(existing_q)
            added.append({"question_id": existing_q.id, "title": existing_q.title, "existed": True})
            continue

        diff_map = {"Easy": Difficulty.EASY, "Medium": Difficulty.MEDIUM, "Hard": Difficulty.HARD}
        difficulty = diff_map.get(fq["difficulty"], Difficulty.MEDIUM)

        question = Question(
            number=fq["number"],
            title=fq["title"],
            difficulty=difficulty,
            topics=[topic] if topic else [st.category],
            subtopics=[st.name],
            url=fq.get("url"),
            frequency=0.5,
            sources=[{"name": "AI-found", "type": "auto"}],
        )
        db.add(question)
        await db.flush()

        try:
            await solution_service.generate_solutions(db, question)
        except Exception as e:
            errors.append({"number": fq["number"], "title": fq["title"], "error": str(e)})

        added.append({"question_id": question.id, "title": question.title, "existed": False})

    await db.commit()
    return {
        "added": added,
        "errors": errors,
        "subtopic": st.name,
    }


@router.post("/sync-taxonomy")
async def sync_taxonomy(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add any missing subtopics from the canonical taxonomy without deleting existing ones."""
    from backend.taxonomy import TAXONOMY
    from backend.models.subtopic import SubtopicKnowledge

    existing_names = set(n.lower() for n in await subtopic_service.get_all_subtopic_names(db))
    created = 0
    for entry in TAXONOMY:
        topic = entry["topic"]
        for st_data in entry["subtopics"]:
            if st_data["name"].lower() in existing_names:
                continue
            st = SubtopicKnowledge(
                name=st_data["name"],
                category=topic,
                description=st_data.get("description"),
                when_to_use=st_data.get("when_to_use"),
                key_signals=st_data.get("key_signals"),
                variants=st_data.get("variants"),
                implementation_keys=st_data.get("implementation_keys"),
                common_pitfalls=st_data.get("common_pitfalls"),
            )
            db.add(st)
            created += 1
    await db.commit()
    return {"subtopics_created": created}


@router.post("/rebuild-taxonomy")
async def rebuild_taxonomy(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete all subtopics and rebuild from the canonical taxonomy.
    Also remaps question subtopics and derives topics."""
    import json
    from sqlalchemy import delete, text

    from backend.taxonomy import (
        OLD_TO_NEW, SUBTOPIC_TO_TOPIC, TAXONOMY,
    )
    from backend.models.subtopic import SubtopicKnowledge

    await db.execute(delete(SubtopicKnowledge))
    created = 0
    for entry in TAXONOMY:
        topic = entry["topic"]
        for st_data in entry["subtopics"]:
            st = SubtopicKnowledge(
                name=st_data["name"],
                category=topic,
                description=st_data.get("description"),
                when_to_use=st_data.get("when_to_use"),
                key_signals=st_data.get("key_signals"),
                variants=st_data.get("variants"),
                implementation_keys=st_data.get("implementation_keys"),
                common_pitfalls=st_data.get("common_pitfalls"),
            )
            db.add(st)
            created += 1

    rows = (await db.execute(
        text("SELECT id, subtopics, topics FROM questions")
    )).fetchall()
    remapped = 0
    for row in rows:
        qid = row[0]
        old_subtopics_raw = row[1]
        try:
            old_subtopics = json.loads(old_subtopics_raw) if old_subtopics_raw else []
        except (json.JSONDecodeError, TypeError):
            old_subtopics = []

        new_subtopics = []
        for s in old_subtopics:
            s_lower = s.strip().lower()
            new_name = OLD_TO_NEW.get(s_lower, s)
            if new_name not in new_subtopics:
                new_subtopics.append(new_name)

        new_topics = []
        for s in new_subtopics:
            t = SUBTOPIC_TO_TOPIC.get(s.lower())
            if t and t not in new_topics:
                new_topics.append(t)
        if not new_topics:
            try:
                old_topics = json.loads(row[2]) if row[2] else []
            except (json.JSONDecodeError, TypeError):
                old_topics = []
            new_topics = old_topics

        await db.execute(text(
            "UPDATE questions SET subtopics = :st, topics = :tp WHERE id = :id"
        ), {"st": json.dumps(new_subtopics), "tp": json.dumps(new_topics), "id": qid})
        remapped += 1

    await db.commit()
    return {
        "subtopics_created": created,
        "questions_remapped": remapped,
    }
