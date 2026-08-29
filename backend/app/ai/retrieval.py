from dataclasses import dataclass

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.evidence_item import EvidenceItem


@dataclass(frozen=True)
class RetrievedEvidence:
    item: EvidenceItem
    score: int


def _query_terms(query: str) -> list[str]:
    return [
        term
        for term in {token.strip().casefold() for token in query.split()}
        if len(term) >= 2
    ]


def retrieve_evidence(
    db: Session,
    case_id,
    query: str,
    *,
    limit: int = 12,
) -> list[RetrievedEvidence]:
    cleaned_query = query.strip()

    if not cleaned_query:
        return []

    terms = _query_terms(cleaned_query)

    conditions = [
        func.lower(EvidenceItem.evidence_reference) == cleaned_query.casefold(),
        func.lower(EvidenceItem.original_record_id) == cleaned_query.casefold(),
        EvidenceItem.searchable_text.ilike(
            f"%{cleaned_query}%",
        ),
    ]

    for term in terms:
        conditions.append(EvidenceItem.searchable_text.ilike(f"%{term}%"))

    candidates = list(
        db.scalars(
            select(EvidenceItem)
            .where(
                EvidenceItem.case_id == case_id,
                or_(*conditions),
            )
            .order_by(
                EvidenceItem.occurred_at.desc().nullslast(),
                EvidenceItem.id,
            )
            .limit(100)
        )
    )

    ranked: list[RetrievedEvidence] = []

    for item in candidates:
        score = 0
        searchable = item.searchable_text.casefold()
        reference = item.evidence_reference.casefold()
        original_id = item.original_record_id.casefold()

        if cleaned_query.casefold() == reference:
            score += 100

        if cleaned_query.casefold() == original_id:
            score += 90

        if cleaned_query.casefold() in searchable:
            score += 50

        for term in terms:
            if term in searchable:
                score += 5

        ranked.append(
            RetrievedEvidence(
                item=item,
                score=score,
            )
        )

    ranked.sort(
        key=lambda result: (
            -result.score,
            result.item.evidence_reference,
        )
    )

    return ranked[:limit]
