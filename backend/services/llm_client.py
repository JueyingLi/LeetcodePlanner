import json
import logging

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.api_config import ApiConfig

logger = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    usage: dict = {}


class LLMClient:
    async def _get_config(self, db: AsyncSession, provider: str | None = None) -> ApiConfig | None:
        # API keys are per-user. Resolve the current user from the request-scoped
        # contextvar set by backend.auth.get_current_user.
        from backend.auth import current_user_id

        user_id = current_user_id.get()
        query = select(ApiConfig)
        if user_id is not None:
            query = query.where(ApiConfig.user_id == user_id)
        if provider:
            query = query.where(ApiConfig.provider == provider)
        else:
            query = query.where(ApiConfig.is_active.is_(True))
        result = await db.execute(query.limit(1))
        return result.scalar_one_or_none()

    def _decrypt_key(self, encrypted_key: str) -> str:
        from backend.config import settings
        if not settings.fernet_key:
            return encrypted_key
        from cryptography.fernet import Fernet
        f = Fernet(settings.fernet_key.encode())
        return f.decrypt(encrypted_key.encode()).decode()

    async def resolve_config(
        self,
        db: AsyncSession,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict:
        config = await self._get_config(db, provider)
        if not config:
            raise ValueError(f"No API key configured for provider: {provider or 'default'}")
        return {
            "provider": config.provider,
            "model": model or config.model,
            "api_key": self._decrypt_key(config.api_key_encrypted),
        }

    async def complete(
        self,
        messages: list[dict],
        db: AsyncSession,
        provider: str | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        cfg = await self.resolve_config(db, provider, model)
        return await self.complete_direct(messages, cfg)

    async def complete_direct(
        self,
        messages: list[dict],
        cfg: dict,
    ) -> LLMResponse:
        if cfg["provider"] == "openai":
            return await self._openai_complete(cfg["api_key"], cfg["model"], messages)
        elif cfg["provider"] == "anthropic":
            return await self._anthropic_complete(cfg["api_key"], cfg["model"], messages)
        else:
            raise ValueError(f"Unknown provider: {cfg['provider']}")

    async def complete_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        db: AsyncSession,
        provider: str | None = None,
        model: str | None = None,
    ) -> BaseModel:
        cfg = await self.resolve_config(db, provider, model)
        return await self.complete_structured_direct(messages, schema, cfg)

    async def complete_structured_direct(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        cfg: dict,
    ) -> BaseModel:
        system_msg = (
            f"Respond ONLY with valid JSON matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
            f"No markdown, no code fences, just raw JSON."
        )
        full_messages = [{"role": "system", "content": system_msg}] + messages
        response = await self.complete_direct(full_messages, cfg)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return schema.model_validate_json(content)

    async def _openai_complete(
        self, api_key: str, model: str, messages: list[dict]
    ) -> LLMResponse:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
        )
        return LLMResponse(
            content=response.choices[0].message.content or "",
            provider="openai",
            model=model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

    async def _anthropic_complete(
        self, api_key: str, model: str, messages: list[dict]
    ) -> LLMResponse:
        client = AsyncAnthropic(api_key=api_key)
        system_text = ""
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system_text += m["content"] + "\n"
            else:
                filtered.append(m)

        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_text.strip() if system_text else "",
            messages=filtered,
            temperature=0.3,
        )
        content = response.content[0].text if response.content else ""
        return LLMResponse(
            content=content,
            provider="anthropic",
            model=model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    async def test_key(self, provider: str, api_key: str) -> tuple[bool, str]:
        try:
            if provider == "openai":
                client = AsyncOpenAI(api_key=api_key)
                await client.models.list()
                return True, "OpenAI API key is valid"
            elif provider == "anthropic":
                client = AsyncAnthropic(api_key=api_key)
                await client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "hi"}],
                )
                return True, "Anthropic API key is valid"
            else:
                return False, f"Unknown provider: {provider}"
        except Exception as e:
            return False, str(e)


llm_client = LLMClient()
