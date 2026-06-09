import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.glossary_agent import GlossaryAgent
from backend.models.glossary import GlossaryTerm
from backend.models.subtopic import SubtopicKnowledge
from backend.taxonomy import OLD_TO_NEW


def _slugify(term: str) -> str:
    s = term.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


async def _subtopic_context(db: AsyncSession, term: str) -> str | None:
    """If the term maps to a known subtopic, pass its curated notes to the agent
    so the generated entry stays accurate to our taxonomy."""
    candidates = {term, OLD_TO_NEW.get(term.strip().lower(), "")}
    for name in candidates:
        if not name:
            continue
        row = (await db.execute(
            select(SubtopicKnowledge).where(func.lower(SubtopicKnowledge.name) == name.strip().lower())
        )).scalar_one_or_none()
        if row and row.description:
            parts = [f"Name: {row.name}", f"What: {row.description}"]
            if row.when_to_use:
                parts.append(f"When to use: {row.when_to_use}")
            if row.implementation_keys:
                parts.append(f"Implementation: {row.implementation_keys}")
            if row.common_pitfalls:
                parts.append(f"Pitfalls: {row.common_pitfalls}")
            return "\n".join(parts)
    return None


async def get_or_create(
    db: AsyncSession,
    term: str,
    provider: str | None = None,
    model: str | None = None,
) -> GlossaryTerm:
    slug = _slugify(term)
    existing = (await db.execute(
        select(GlossaryTerm).where(GlossaryTerm.slug == slug)
    )).scalar_one_or_none()
    if existing:
        return existing

    context = await _subtopic_context(db, term)
    agent = GlossaryAgent()
    entry = await agent.generate(db, term, context, provider, model)

    glossary_term = GlossaryTerm(
        slug=slug,
        name=term.strip(),
        definition=entry.definition,
        how_it_works=entry.how_it_works,
        example=entry.example,
    )
    db.add(glossary_term)
    await db.commit()
    await db.refresh(glossary_term)
    return glossary_term
