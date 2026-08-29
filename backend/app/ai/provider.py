import json
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import settings


@dataclass(frozen=True)
class EvidenceContextItem:
    evidence_reference: str
    artifact_type: str
    application: str | None
    occurred_at: str | None
    searchable_excerpt: str
    normalized_data_excerpt: str


@dataclass(frozen=True)
class ProviderAnswer:
    answer: str
    citations: tuple[str, ...]
    insufficient_evidence: bool


class AIProvider(Protocol):
    def answer(
        self,
        question: str,
        evidence: tuple[EvidenceContextItem, ...],
    ) -> ProviderAnswer: ...


class ProviderError(Exception):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class _StructuredProviderResponse(BaseModel):
    answer: str = Field(min_length=1, max_length=8_000)
    citations: list[str] = Field(default_factory=list, max_length=50)
    insufficient_evidence: bool


class DisabledAIProvider:
    def __init__(self, reason: str = "AI provider is disabled") -> None:
        self.reason = reason

    def answer(
        self,
        question: str,
        evidence: tuple[EvidenceContextItem, ...],
    ) -> ProviderAnswer:
        raise ProviderUnavailableError(self.reason)


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def answer(
        self,
        question: str,
        evidence: tuple[EvidenceContextItem, ...],
    ) -> ProviderAnswer:
        context = [
            {
                "evidence_reference": item.evidence_reference,
                "artifact_type": item.artifact_type,
                "application": item.application,
                "occurred_at": item.occurred_at,
                "searchable_excerpt": item.searchable_excerpt,
                "normalized_data_excerpt": item.normalized_data_excerpt,
            }
            for item in evidence
        ]
        payload = {
            "model": self.model,
            "store": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are ForenSight, a forensic investigation assistant. "
                        "Use only the supplied evidence context. Never invent facts or "
                        "evidence references. Cite only evidence_reference values from "
                        "the context. If the evidence does not support an answer, set "
                        "insufficient_evidence to true and state that evidence is insufficient."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"question": question, "evidence_context": context},
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "forensight_grounded_answer",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "answer": {"type": "string"},
                            "citations": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "insufficient_evidence": {"type": "boolean"},
                        },
                        "required": [
                            "answer",
                            "citations",
                            "insufficient_evidence",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
        }

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = _StructuredProviderResponse.model_validate_json(content)
        except (
            httpx.HTTPError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValidationError,
        ) as exc:
            raise ProviderError("AI provider request or response was invalid") from exc

        answer = parsed.answer.strip()
        if not answer:
            raise ProviderError("AI provider returned an empty answer")

        return ProviderAnswer(
            answer=answer,
            citations=tuple(parsed.citations),
            insufficient_evidence=parsed.insufficient_evidence,
        )


def get_ai_provider() -> AIProvider:
    provider_name = settings.ai_provider.strip().lower()
    if provider_name in {"", "disabled", "none"}:
        return DisabledAIProvider()
    if provider_name not in {"openai", "openai_compatible"}:
        return DisabledAIProvider("Configured AI provider is unsupported")
    if settings.ai_api_key is None or not settings.ai_api_key.get_secret_value():
        return DisabledAIProvider("AI API key is not configured")
    if not settings.ai_model:
        return DisabledAIProvider("AI model is not configured")
    return OpenAICompatibleProvider(
        api_key=settings.ai_api_key.get_secret_value(),
        model=settings.ai_model,
        base_url=settings.ai_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
    )
