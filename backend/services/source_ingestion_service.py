import html
import os
import re
import time
from typing import Any

import httpx
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.agents.parser_agent import ParserAgent
from backend.models.question import Question
from backend.models.study_plan import QuestionSourcePost
from backend.schemas.question import QuestionCreate, QuestionUpdate, SourceTag
from backend.services import question_service, subtopic_service

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql/"
PAGE_SIZE = 50
SLEEP_SECONDS = 1.0

SEARCH_QUERY = """
query discussPostItems(
  $orderBy: ArticleOrderByEnum,
  $keywords: [String]!,
  $tagSlugs: [String!],
  $skip: Int,
  $first: Int
) {
  ugcArticleDiscussionArticles(
    orderBy: $orderBy,
    keywords: $keywords,
    tagSlugs: $tagSlugs,
    skip: $skip,
    first: $first
  ) {
    totalNum
    pageInfo { hasNextPage }
    edges {
      node {
        uuid
        title
        slug
        summary
        createdAt
        updatedAt
        hitCount
        topicId
        articleType
        status
        tags { name slug tagType }
        topic { id topLevelCommentCount }
        reactions { count reactionType }
      }
    }
  }
}
"""

DETAIL_QUERIES = [
    """
    query discussionArticle($uuid: String!) {
      ugcArticleDiscussionArticle(uuid: $uuid) {
        uuid title slug content summary createdAt updatedAt topicId
        topic { id topLevelCommentCount }
      }
    }
    """,
    """
    query discussionArticle($slug: String!) {
      ugcArticleDiscussionArticle(slug: $slug) {
        uuid title slug content summary createdAt updatedAt topicId
        topic { id topLevelCommentCount }
      }
    }
    """,
]

COMMENT_QUERIES = [
    """
    query discussionComments($topicId: Int!, $skip: Int, $first: Int) {
      ugcArticleComments(topicId: $topicId, skip: $skip, first: $first) {
        totalNum
        pageInfo { hasNextPage }
        edges {
          node { id content createdAt updatedAt author { userName userSlug } }
        }
      }
    }
    """,
    """
    query discussionComments($topicId: ID!, $skip: Int, $first: Int) {
      ugcArticleComments(topicId: $topicId, skip: $skip, first: $first) {
        totalNum
        pageInfo { hasNextPage }
        edges {
          node { id content createdAt updatedAt author { userName userSlug } }
        }
      }
    }
    """,
]


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def usefulness_score(post: dict[str, Any], full_text: str) -> int:
    title = clean_text(post.get("title")).lower()
    summary = clean_text(post.get("summary")).lower()
    text = full_text.lower()
    tags = " ".join(t.get("slug", "") for t in post.get("tags", [])).lower()
    score = 0

    strong_signals = [
        "interview experience", "onsite", "phone screen", "asked", "question was",
        "problem statement", "round 1", "round 2", "r1", "r2", "l4", "swe",
        "usa", "mountainview", "mountain view",
    ]
    problem_signals = [
        "given", "return", "design a", "data structure", "stream", "array",
        "tree", "graph", "bfs", "dfs", "dp", "sliding window", "binary search",
        "follow up",
    ]
    noise = [
        "prep partner", "need leetcode premium", "team match", "how long",
        "offer", "hiring process", "application engineer", "intern",
        "university graduate",
    ]

    for signal in strong_signals:
        if signal in title or signal in summary or signal in text:
            score += 3
    for signal in problem_signals:
        if signal in summary or signal in text:
            score += 2
    for signal in noise:
        if signal in title or signal in summary:
            score -= 4
    if "google" in tags:
        score += 2
    if "l4-google" in tags:
        score += 3
    if "google-interview-questions" in tags:
        score += 1
    if post.get("topic", {}).get("topLevelCommentCount", 0) >= 3:
        score += 1
    return score


def extract_question_like_lines(text: str) -> list[str]:
    text = clean_text(text)
    patterns = [
        r"(?:Question|Problem|Round \d+|R\d+)[^.!?]{0,220}[.!?]",
        r"(?:Given|Design|Implement|Find|Return|You are given)[^.!?]{20,360}[.!?]",
        r"[^.!?]*(?:BFS|DFS|graph|tree|array|stream|timestamp|deduplicate|sliding window|binary search|DP|segment tree|union find)[^.!?]*[.!?]",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text, flags=re.IGNORECASE))

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in found:
        item = clean_text(item)
        key = item.lower()
        if 30 <= len(item) <= 600 and key not in seen:
            cleaned.append(item)
            seen.add(key)
    return cleaned[:12]


async def _graphql(
    client: httpx.AsyncClient,
    query: str,
    variables: dict[str, Any],
    operation_name: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query, "variables": variables}
    if operation_name:
        payload["operationName"] = operation_name
    response = await client.post(LEETCODE_GRAPHQL_URL, json=payload)
    response.raise_for_status()
    data = response.json()
    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))
    return data


async def _search_discussions(client: httpx.AsyncClient, keywords: list[str], max_results: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    skip = 0
    while len(results) < max_results:
        first = min(PAGE_SIZE, max_results - len(results))
        data = await _graphql(
            client,
            SEARCH_QUERY,
            {
                "orderBy": "NEWEST_TO_OLDEST",
                "keywords": keywords,
                "tagSlugs": ["google-interview-questions"],
                "skip": skip,
                "first": first,
            },
            "discussPostItems",
        )
        container = data["data"]["ugcArticleDiscussionArticles"]
        edges = container.get("edges", [])
        for edge in edges:
            results.append(edge["node"])
        if not container.get("pageInfo", {}).get("hasNextPage") or not edges:
            break
        skip += first
        time.sleep(SLEEP_SECONDS)
    return results[:max_results]


async def _try_fetch_detail(client: httpx.AsyncClient, post: dict[str, Any]) -> dict[str, Any]:
    for query in DETAIL_QUERIES:
        variables: dict[str, Any] = {}
        if "$uuid" in query:
            variables["uuid"] = post.get("uuid")
        if "$slug" in query:
            variables["slug"] = post.get("slug")
        try:
            data = await _graphql(client, query, variables)
            article = data.get("data", {}).get("ugcArticleDiscussionArticle")
            if article:
                return article
        except Exception:
            continue
    return {}


async def _try_fetch_comments(client: httpx.AsyncClient, topic_id: int | None, max_comments: int) -> list[dict[str, Any]]:
    if not topic_id or max_comments <= 0:
        return []
    for query in COMMENT_QUERIES:
        comments: list[dict[str, Any]] = []
        try:
            skip = 0
            while len(comments) < max_comments:
                first = min(20, max_comments - len(comments))
                data = await _graphql(client, query, {"topicId": topic_id, "skip": skip, "first": first})
                container = data.get("data", {}).get("ugcArticleComments")
                if not container:
                    break
                edges = container.get("edges", [])
                for edge in edges:
                    comments.append(edge["node"])
                if not container.get("pageInfo", {}).get("hasNextPage") or not edges:
                    break
                skip += first
                time.sleep(SLEEP_SECONDS)
            return comments
        except Exception:
            continue
    return []


def _source_tags(post_title: str | None = None) -> list[SourceTag]:
    tags = [
        SourceTag(name="Google discussion", type="company"),
        SourceTag(name="Google recent", type="company"),
        SourceTag(name="Google L4", type="company"),
    ]
    if post_title:
        tags.append(SourceTag(name=f"Discussion: {post_title[:80]}", type="discussion"))
    return tags


async def _find_question_by_title(db: AsyncSession, title: str) -> Question | None:
    normalized = re.sub(r"\s+", " ", title.strip()).lower()
    result = await db.execute(
        select(Question).where(func_lower(Question.title) == normalized)
    )
    return result.scalar_one_or_none()


def func_lower(column):
    from sqlalchemy import func

    return func.lower(func.trim(column))


async def _merge_questions_from_text(
    db: AsyncSession,
    text: str,
    source_title: str | None,
) -> dict[str, int]:
    agent = ParserAgent()
    try:
        parsed = await agent.parse(db, text, "Google discussion")
    except Exception:
        parsed = []

    if not parsed:
        lines = extract_question_like_lines(text)
        parsed = [
            QuestionCreate(
                title=line[:220],
                difficulty="Medium",
                topics=[],
                subtopics=[],
                frequency=0.75,
                sources=_source_tags(source_title),
                notes=line,
            )
            for line in lines
        ]

    added = updated = skipped = 0
    for q_data in parsed:
        q_data.sources = _merge_source_tags(q_data.sources, _source_tags(source_title))
        q_data.frequency = max(q_data.frequency or 0, 0.75)
        existing = None
        if q_data.number:
            existing = await question_service.get_question_by_number(db, q_data.number)
        if not existing:
            existing = await _find_question_by_title(db, q_data.title)

        if existing:
            update_data: dict[str, Any] = {}
            merged_sources = _merge_raw_sources(existing.sources or [], [s.model_dump() for s in q_data.sources])
            if merged_sources != (existing.sources or []):
                update_data["sources"] = merged_sources
            if (q_data.frequency or 0) > (existing.frequency or 0):
                update_data["frequency"] = q_data.frequency
            if q_data.subtopics:
                merged_subtopics = sorted(set(existing.subtopics or []) | set(q_data.subtopics))
                if merged_subtopics != (existing.subtopics or []):
                    update_data["subtopics"] = merged_subtopics
            if update_data:
                await question_service.update_question(db, existing.id, QuestionUpdate(**update_data))
                updated += 1
            else:
                skipped += 1
            continue

        created = await question_service.create_question(db, q_data)
        added += 1
        if q_data.subtopics:
            primary_topic = q_data.topics[0] if q_data.topics else "Uncategorized"
            await subtopic_service.ensure_subtopics_exist(db, q_data.subtopics, primary_topic)
        _ = created

    return {"questions_added": added, "questions_updated": updated, "questions_skipped": skipped}


def _merge_source_tags(existing: list[SourceTag], incoming: list[SourceTag]) -> list[SourceTag]:
    by_name = {s.name: s for s in existing}
    for src in incoming:
        by_name.setdefault(src.name, src)
    return list(by_name.values())


def _merge_raw_sources(existing: list[Any], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in list(existing or []) + incoming:
        raw = src if isinstance(src, dict) else {"name": src.name, "type": src.type}
        name = raw.get("name")
        if not name or name in seen:
            continue
        output.append({"name": name, "type": raw.get("type", "list")})
        seen.add(name)
    return output


async def _upsert_post(db: AsyncSession, user_id: str, data: dict[str, Any]) -> tuple[QuestionSourcePost, bool]:
    filters = []
    if data.get("uuid"):
        filters.append(QuestionSourcePost.uuid == data["uuid"])
    if data.get("topic_id"):
        filters.append(QuestionSourcePost.topic_id == data["topic_id"])
    if data.get("url"):
        filters.append(QuestionSourcePost.url == data["url"])

    existing = None
    if filters:
        existing = (await db.execute(
            select(QuestionSourcePost).where(
                QuestionSourcePost.user_id == user_id,
                or_(*filters),
            )
        )).scalar_one_or_none()

    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        await db.commit()
        await db.refresh(existing)
        return existing, False

    post = QuestionSourcePost(user_id=user_id, **data)
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post, True


async def import_pasted_source(
    db: AsyncSession, user_id: str, text: str, title: str | None = None, url: str | None = None
) -> dict[str, Any]:
    cleaned = clean_text(text)
    extracted = extract_question_like_lines(cleaned)
    score = usefulness_score({"title": title or "Pasted Google discussion", "summary": cleaned[:500], "tags": []}, cleaned)
    post, added = await _upsert_post(
        db,
        user_id,
        {
            "source_type": "paste",
            "title": title or "Pasted Google discussion",
            "url": url,
            "summary": cleaned[:1000],
            "full_text_preview": cleaned[:4000],
            "score": score,
            "extracted_questions": extracted,
            "raw_json": {"text": cleaned[:12000]},
        },
    )
    counts = await _merge_questions_from_text(db, "\n".join(extracted) if extracted else cleaned, post.title)
    return {
        "posts_added": 1 if added else 0,
        "posts_updated": 0 if added else 1,
        **counts,
        "posts": [post],
    }


async def scrape_leetcode_sources(
    db: AsyncSession, user_id: str, max_results: int = 200, max_comments: int = 20
) -> dict[str, Any]:
    cookie = (os.environ.get("LEETCODE_COOKIE") or settings.leetcode_cookie or "").strip()
    csrf = (os.environ.get("LEETCODE_CSRF") or settings.leetcode_csrf or "").strip()
    if not cookie:
        raise RuntimeError("Missing LEETCODE_COOKIE env var. Paste/import is still available.")

    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://leetcode.com",
        "referer": "https://leetcode.com/discuss/topic/google-interview-questions/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "cookie": cookie,
    }
    if csrf:
        headers["x-csrftoken"] = csrf

    search_configs = [
        ["google l4 onsite"],
        ["google l4 usa"],
        ["google swe l4 interview"],
        ["google recently asked"],
        ["google interview question L4"],
    ]
    deduped: dict[str, dict[str, Any]] = {}
    per_search = max(1, max_results // len(search_configs))
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        for keywords in search_configs:
            posts = await _search_discussions(client, keywords, per_search)
            for post in posts:
                key = post.get("uuid") or str(post.get("topicId")) or post.get("slug")
                if key:
                    deduped[key] = post
            time.sleep(SLEEP_SECONDS)

        useful_posts: list[QuestionSourcePost] = []
        posts_added = posts_updated = 0
        question_counts = {"questions_added": 0, "questions_updated": 0, "questions_skipped": 0}
        for post in deduped.values():
            detail = await _try_fetch_detail(client, post)
            topic_id = (
                post.get("topic", {}).get("id")
                or post.get("topicId")
                or detail.get("topic", {}).get("id")
                or detail.get("topicId")
            )
            comments = await _try_fetch_comments(client, topic_id, max_comments)
            content = clean_text(detail.get("content"))
            summary = clean_text(post.get("summary"))
            comment_text = " ".join(clean_text(c.get("content")) for c in comments)
            full_text = " ".join([summary, content, comment_text]).strip()
            extracted = extract_question_like_lines(full_text)
            score = usefulness_score(post, full_text)
            if score < 5 and not extracted:
                continue

            url = f"https://leetcode.com/discuss/post/{post.get('topicId')}/{post.get('slug')}/"
            persisted, added = await _upsert_post(
                db,
                user_id,
                {
                    "source_type": "leetcode_graphql",
                    "uuid": post.get("uuid"),
                    "topic_id": post.get("topicId") or topic_id,
                    "slug": post.get("slug"),
                    "title": clean_text(post.get("title")) or "LeetCode discussion",
                    "url": url,
                    "summary": summary,
                    "full_text_preview": full_text[:4000],
                    "created_at_from_source": post.get("createdAt"),
                    "updated_at_from_source": post.get("updatedAt"),
                    "hit_count": post.get("hitCount"),
                    "comment_count": post.get("topic", {}).get("topLevelCommentCount"),
                    "score": score,
                    "extracted_questions": extracted,
                    "raw_json": {"post": post, "detail": detail, "comments": comments[:max_comments]},
                },
            )
            useful_posts.append(persisted)
            posts_added += 1 if added else 0
            posts_updated += 0 if added else 1
            counts = await _merge_questions_from_text(db, "\n".join(extracted) if extracted else full_text, persisted.title)
            for key in question_counts:
                question_counts[key] += counts[key]
            time.sleep(SLEEP_SECONDS)

    return {
        "posts_added": posts_added,
        "posts_updated": posts_updated,
        **question_counts,
        "posts": useful_posts[:50],
    }


async def list_source_posts(db: AsyncSession, user_id: str, limit: int = 50) -> list[QuestionSourcePost]:
    result = await db.execute(
        select(QuestionSourcePost)
        .where(QuestionSourcePost.user_id == user_id)
        .order_by(QuestionSourcePost.imported_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
