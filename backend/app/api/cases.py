import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.access import require_case_modify, require_case_view
from app.db.session import get_db
from app.models.case import Case
from app.models.user import User
from app.schemas import CaseCreate, CaseResponse, CaseUpdate

router = APIRouter(prefix="/cases", tags=["cases"])


def _owned_case(db: Session, case_id: uuid.UUID, owner_id: uuid.UUID) -> Case:
    case = db.scalar(
        select(Case).where(Case.id == case_id, Case.owner_id == owner_id)
    )
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _new_case_identifier() -> str:
    date = datetime.now(UTC).strftime("%Y%m%d")
    return f"FS-{date}-{uuid.uuid4().hex[:8].upper()}"


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Case:
    case = Case(
        case_identifier=_new_case_identifier(),
        name=payload.name,
        description=payload.description,
        owner_id=current_user.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("", response_model=list[CaseResponse])
def list_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Case]:
    return list(
        db.scalars(
            select(Case)
            .where(Case.owner_id == current_user.id)
            .order_by(Case.updated_at.desc())
        )
    )


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Case:
    return require_case_view(db, case_id, current_user.id).case


@router.patch("/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: uuid.UUID,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Case:
    case = require_case_modify(db, case_id, current_user.id).case
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    return case
