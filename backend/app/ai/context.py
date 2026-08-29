import json

from app.ai.provider import EvidenceContextItem
from app.ai.retrieval import RetrievedEvidence
from app.config import settings


def _bounded_text(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1]}…"


def build_evidence_context(
    retrieved: list[RetrievedEvidence],
) -> tuple[EvidenceContextItem, ...]:
    items = []
    for result in retrieved[: settings.ai_context_max_items]:
        evidence = result.item
        normalized_json = json.dumps(
            evidence.data,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        items.append(
            EvidenceContextItem(
                evidence_reference=evidence.evidence_reference,
                artifact_type=evidence.artifact_type,
                application=evidence.application,
                occurred_at=(
                    evidence.occurred_at.isoformat()
                    if evidence.occurred_at
                    else None
                ),
                searchable_excerpt=_bounded_text(
                    evidence.searchable_text,
                    settings.ai_context_excerpt_chars,
                ),
                normalized_data_excerpt=_bounded_text(
                    normalized_json,
                    settings.ai_context_data_chars,
                ),
            )
        )
    return tuple(items)
