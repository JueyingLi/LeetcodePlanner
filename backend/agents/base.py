import logging

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.llm_client import llm_client

logger = logging.getLogger(__name__)


class BaseLLMAgent:
    async def call_llm(
        self,
        messages: list[dict],
        db: AsyncSession,
        provider: str | None = None,
        model: str | None = None,
    ) -> str:
        response = await llm_client.complete(messages, db, provider, model)
        return response.content

    async def call_llm_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        db: AsyncSession,
        provider: str | None = None,
        model: str | None = None,
    ) -> BaseModel:
        return await llm_client.complete_structured(messages, schema, db, provider, model)

    async def call_llm_structured_direct(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        cfg: dict,
    ) -> BaseModel:
        return await llm_client.complete_structured_direct(messages, schema, cfg)
