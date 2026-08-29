import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.context import build_evidence_context
from app.ai.grounding import build_grounded_fallback
from app.ai.provider import AIProvider, ProviderError, get_ai_provider
from app.ai.retrieval import retrieve_evidence
from app.access import require_case_view
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas import (
    AskCitationResponse,
    AskRequest,
    AskResponse,
)

router = APIRouter(
    prefix="/cases/{case_id}/ask",
    tags=["ask"],
)


@router.post(
    "",
    response_model=AskResponse,
)
def ask_forensight(
    case_id: uuid.UUID,
    request: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: AIProvider = Depends(get_ai_provider),
) -> AskResponse:
    access = require_case_view(
        db,
        case_id,
        current_user.id,
    )

    retrieved = retrieve_evidence(
        db,
        access.evidence_case_id,
        request.query,
    )

    grounded = build_grounded_fallback(
        request.query,
        retrieved,
    )

    fallback_response = AskResponse(
        answer=grounded.answer,
        sufficient_evidence=grounded.sufficient_evidence,
        citations=[
            AskCitationResponse(
                evidence_id=citation.evidence_id,
                evidence_reference=citation.evidence_reference,
                source_id=citation.source_id,
                artifact_type=citation.artifact_type,
                occurred_at=citation.occurred_at,
                application=citation.application,
                excerpt=citation.excerpt,
            )
            for citation in grounded.citations
        ],
    )
    if not grounded.sufficient_evidence:
        return fallback_response

    try:
        provider_answer = provider.answer(
            request.query,
            build_evidence_context(retrieved),
        )
    except ProviderError:
        return fallback_response

    if provider_answer.insufficient_evidence:
        return AskResponse(
            answer=provider_answer.answer,
            sufficient_evidence=False,
            citations=[],
        )

    citation_by_reference = {
        citation.evidence_reference: citation
        for citation in grounded.citations
    }
    valid_citations = []
    seen_references: set[str] = set()
    for reference in provider_answer.citations:
        citation = citation_by_reference.get(reference)
        if citation is not None and reference not in seen_references:
            valid_citations.append(citation)
            seen_references.add(reference)

    if not valid_citations:
        return fallback_response

    return AskResponse(
        answer=provider_answer.answer,
        sufficient_evidence=True,
        citations=[
            AskCitationResponse(
                evidence_id=citation.evidence_id,
                evidence_reference=(
                    citation.evidence_reference
                ),
                source_id=citation.source_id,
                artifact_type=citation.artifact_type,
                occurred_at=citation.occurred_at,
                application=citation.application,
                excerpt=citation.excerpt,
            )
            for citation in valid_citations
        ],
    )
