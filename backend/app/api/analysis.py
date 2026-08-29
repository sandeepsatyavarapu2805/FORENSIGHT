import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.engine import (
    build_entities,
    build_relationships,
    build_timeline,
    source_warnings,
)
from app.access import require_case_view
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.user import User
from app.schemas import (
    AnalysisEntityResponse,
    AnalysisOverviewResponse,
    RelationshipResponse,
    TimelineEntryResponse,
)

router = APIRouter(
    prefix="/cases/{case_id}/analysis",
    tags=["analysis"],
)


def _case_evidence(
    db: Session,
    case_id: uuid.UUID,
) -> list[EvidenceItem]:
    return list(
        db.scalars(
            select(EvidenceItem).where(
                EvidenceItem.case_id == case_id,
            )
        )
    )


def _case_sources(
    db: Session,
    case_id: uuid.UUID,
) -> list[EvidenceSource]:
    return list(
        db.scalars(
            select(EvidenceSource).where(
                EvidenceSource.case_id == case_id,
            )
        )
    )


@router.get(
    "",
    response_model=AnalysisOverviewResponse,
)
def analysis_overview(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalysisOverviewResponse:
    access = require_case_view(db, case_id, current_user.id)

    evidence = _case_evidence(db, access.evidence_case_id)
    sources = _case_sources(db, access.evidence_case_id)

    entities = build_entities(evidence)
    timeline = build_timeline(evidence)
    relationships = build_relationships(evidence)

    return AnalysisOverviewResponse(
        entities=[
            AnalysisEntityResponse(
                key=item.key,
                entity_type=item.entity_type,
                value=item.value,
                evidence_ids=list(item.evidence_ids),
                evidence_references=list(
                    item.evidence_references
                ),
                occurrence_count=item.occurrence_count,
            )
            for item in entities
        ],
        timeline=[
            TimelineEntryResponse(
                evidence_id=item.evidence_id,
                evidence_reference=item.evidence_reference,
                source_id=item.source_id,
                artifact_type=item.artifact_type,
                application=item.application,
                occurred_at=item.occurred_at,
                searchable_text=item.searchable_text,
            )
            for item in timeline
        ],
        relationships=[
            RelationshipResponse(
                source_key=item.source_key,
                target_key=item.target_key,
                relationship_type=item.relationship_type,
                evidence_ids=list(item.evidence_ids),
                evidence_references=list(
                    item.evidence_references
                ),
                occurrence_count=item.occurrence_count,
            )
            for item in relationships
        ],
        warnings=source_warnings(sources),
    )
