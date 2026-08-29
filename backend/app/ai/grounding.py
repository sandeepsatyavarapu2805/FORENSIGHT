from dataclasses import dataclass

from app.ai.retrieval import RetrievedEvidence


@dataclass(frozen=True)
class GroundedCitation:
    evidence_id: str
    evidence_reference: str
    source_id: str
    artifact_type: str
    occurred_at: str | None
    application: str | None
    excerpt: str


@dataclass(frozen=True)
class GroundedAnswer:
    answer: str
    sufficient_evidence: bool
    citations: tuple[GroundedCitation, ...]


def _excerpt(text: str, *, limit: int = 280) -> str:
    cleaned = " ".join(text.split())

    if len(cleaned) <= limit:
        return cleaned

    return f"{cleaned[:limit - 1]}…"


def build_grounded_fallback(
    query: str,
    retrieved: list[RetrievedEvidence],
) -> GroundedAnswer:
    if not retrieved:
        return GroundedAnswer(
            answer=(
                "Insufficient evidence was found in the current case "
                "to answer this question. Try a more specific term, "
                "identifier, person, application, date, or evidence reference."
            ),
            sufficient_evidence=False,
            citations=(),
        )

    citations = tuple(
        GroundedCitation(
            evidence_id=str(result.item.id),
            evidence_reference=result.item.evidence_reference,
            source_id=str(result.item.source_id),
            artifact_type=result.item.artifact_type,
            occurred_at=(
                result.item.occurred_at.isoformat()
                if result.item.occurred_at
                else None
            ),
            application=result.item.application,
            excerpt=_excerpt(
                result.item.searchable_text
            ),
        )
        for result in retrieved
    )

    references = ", ".join(
        citation.evidence_reference
        for citation in citations[:5]
    )

    return GroundedAnswer(
        answer=(
            f"ForenSight found {len(citations)} evidence record"
            f"{'' if len(citations) == 1 else 's'} relevant to "
            f"the query \"{query}\". Review the cited evidence "
            f"records before drawing an investigative conclusion. "
            f"Top evidence references: {references}."
        ),
        sufficient_evidence=True,
        citations=citations,
    )