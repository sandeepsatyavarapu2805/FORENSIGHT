import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cases import _owned_case
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.case import Case
from app.models.evidence_source import EvidenceSource
from app.models.user import User
from app.schemas import SourceCreate, SourceResponse, SourceUpdate

router = APIRouter(prefix="/cases/{case_id}/sources", tags=["evidence sources"])


def _owned_source(
    db: Session, case_id: uuid.UUID, source_id: uuid.UUID, owner_id: uuid.UUID
) -> EvidenceSource:
    source = db.scalar(
        select(EvidenceSource)
        .join(EvidenceSource.case)
        .where(
            EvidenceSource.id == source_id,
            EvidenceSource.case_id == case_id,
            Case.owner_id == owner_id,
        )
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source

@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(
    case_id: uuid.UUID,
    payload: SourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceSource:
    _owned_case(db, case_id, current_user.id)
    source = EvidenceSource(case_id=case_id, **payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("", response_model=list[SourceResponse])
def list_sources(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EvidenceSource]:
    _owned_case(db, case_id, current_user.id)
    return list(
        db.scalars(
            select(EvidenceSource)
            .where(EvidenceSource.case_id == case_id)
            .order_by(EvidenceSource.created_at.desc())
        )
    )


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(
    case_id: uuid.UUID,
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceSource:
    return _owned_source(db, case_id, source_id, current_user.id)


@router.patch("/{source_id}", response_model=SourceResponse)
def update_source(
    case_id: uuid.UUID,
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvidenceSource:
    source = _owned_source(db, case_id, source_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    db.commit()
    db.refresh(source)
    return source
