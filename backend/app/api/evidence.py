import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.cases import _owned_case
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.evidence_item import EvidenceItem
from app.models.user import User
from app.schemas import (
    EvidenceFilterOptionsResponse,
    EvidenceItemResponse,
    EvidenceItemSummary,
    EvidencePageResponse,
)

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["evidence"])


@router.get("/filters", response_model=EvidenceFilterOptionsResponse)
def get_evidence_filter_options(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceFilterOptionsResponse:
    _owned_case(db, case_id, current_user.id)

    artifact_types = list(
        db.scalars(
            select(EvidenceItem.artifact_type)
            .where(EvidenceItem.case_id == case_id)
            .distinct()
            .order_by(EvidenceItem.artifact_type)
        )
    )

    applications = list(
        db.scalars(
            select(EvidenceItem.application)
            .where(
                EvidenceItem.case_id == case_id,
                EvidenceItem.application.is_not(None),
            )
            .distinct()
            .order_by(EvidenceItem.application)
        )
    )

    return EvidenceFilterOptionsResponse(
        artifact_types=artifact_types,
        applications=[application for application in applications if application],
    )


@router.get("/by-reference/{evidence_reference}", response_model=EvidenceItemResponse)
def get_evidence_by_reference(
    case_id: uuid.UUID,
    evidence_reference: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceItem:
    _owned_case(db, case_id, current_user.id)

    normalized_reference = evidence_reference.strip()

    evidence = db.scalar(
        select(EvidenceItem).where(
            EvidenceItem.case_id == case_id,
            func.lower(EvidenceItem.evidence_reference) == normalized_reference.lower(),
        )
    )

    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found",
        )

    return evidence


@router.get("", response_model=EvidencePageResponse)
def list_case_evidence(
    case_id: uuid.UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    source_id: uuid.UUID | None = None,
    artifact_type: str | None = Query(default=None, min_length=1, max_length=50),
    application: str | None = Query(default=None, min_length=1, max_length=150),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    query: str | None = Query(default=None, min_length=1, max_length=200),
    sort: Literal["newest", "oldest"] = "newest",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidencePageResponse:
    _owned_case(db, case_id, current_user.id)

    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date_from must not be later than date_to",
        )

    filters = [EvidenceItem.case_id == case_id]

    if source_id is not None:
        filters.append(EvidenceItem.source_id == source_id)

    if artifact_type is not None:
        filters.append(EvidenceItem.artifact_type == artifact_type.strip().lower())

    if application is not None:
        filters.append(
            func.lower(EvidenceItem.application) == application.strip().lower()
        )

    if date_from is not None:
        filters.append(EvidenceItem.occurred_at >= date_from)

    if date_to is not None:
        filters.append(EvidenceItem.occurred_at <= date_to)

    if query is not None:
        search_term = query.strip()

        escaped_term = (
            search_term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )

        filters.append(
            or_(
                func.lower(EvidenceItem.evidence_reference) == search_term.lower(),
                func.lower(EvidenceItem.original_record_id) == search_term.lower(),
                EvidenceItem.searchable_text.ilike(
                    f"%{escaped_term}%",
                    escape="\\",
                ),
            )
        )

    total = (
        db.scalar(select(func.count()).select_from(EvidenceItem).where(*filters)) or 0
    )

    timestamp_order = (
        EvidenceItem.occurred_at.asc().nullslast()
        if sort == "oldest"
        else EvidenceItem.occurred_at.desc().nullslast()
    )

    items = list(
        db.scalars(
            select(EvidenceItem)
            .where(*filters)
            .order_by(timestamp_order, EvidenceItem.id)
            .offset(offset)
            .limit(limit)
        )
    )


    return EvidencePageResponse(
    items=[EvidenceItemSummary.model_validate(item) for item in items],
    total=total,
    offset=offset,
    limit=limit,
    )


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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found",
        )

    return evidence
