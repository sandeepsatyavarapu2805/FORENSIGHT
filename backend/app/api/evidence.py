import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.cases import _owned_case
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.evidence_item import EvidenceItem
from app.models.user import User
from app.schemas import EvidenceItemResponse, EvidencePageResponse

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["evidence"])


@router.get("", response_model=EvidencePageResponse)
def list_case_evidence(
    case_id: uuid.UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    source_id: uuid.UUID | None = None,
    artifact_type: str | None = Query(default=None, min_length=1, max_length=50),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    query: str | None = Query(default=None, min_length=1, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidencePageResponse:
    _owned_case(db, case_id, current_user.id)
    filters = [EvidenceItem.case_id == case_id]
    if source_id is not None:
        filters.append(EvidenceItem.source_id == source_id)
    if artifact_type is not None:
        filters.append(EvidenceItem.artifact_type == artifact_type.strip().lower())
    if date_from is not None:
        filters.append(EvidenceItem.occurred_at >= date_from)
    if date_to is not None:
        filters.append(EvidenceItem.occurred_at <= date_to)
    if query is not None:
        filters.append(EvidenceItem.searchable_text.ilike(f"%{query.strip()}%"))

    total = db.scalar(select(func.count()).select_from(EvidenceItem).where(*filters)) or 0
    items = list(
        db.scalars(
            select(EvidenceItem)
            .where(*filters)
            .order_by(EvidenceItem.occurred_at.desc().nullslast(), EvidenceItem.id)
            .offset(offset)
            .limit(limit)
        )
    )
    return EvidencePageResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/{evidence_id}", response_model=EvidenceItemResponse)
def get_case_evidence(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceItem:
    _owned_case(db, case_id, current_user.id)
    evidence = db.scalar(
        select(EvidenceItem).where(
            EvidenceItem.id == evidence_id,
            EvidenceItem.case_id == case_id,
        )
    )
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found"
        )
    return evidence
