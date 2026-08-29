import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.case_access_grant import CaseAccessGrant


class CaseAccessLevel(StrEnum):
    OWNER = "owner"
    TEMPORARY_READ_ONLY = "temporary_read_only"
    COPY_OWNER = "copy_owner"


@dataclass(frozen=True)
class CaseAccess:
    case: Case
    level: CaseAccessLevel
    evidence_case_id: uuid.UUID
    grant: CaseAccessGrant | None = None

    @property
    def can_view(self) -> bool:
        return True

    @property
    def can_modify(self) -> bool:
        return self.level in {CaseAccessLevel.OWNER, CaseAccessLevel.COPY_OWNER}

    @property
    def is_original_owner(self) -> bool:
        return self.level == CaseAccessLevel.OWNER

    @property
    def is_temporary(self) -> bool:
        return self.level == CaseAccessLevel.TEMPORARY_READ_ONLY


def resolve_case_access(
    db: Session, case_id: uuid.UUID, user_id: uuid.UUID, *, now: datetime | None = None
) -> CaseAccess | None:
    case = db.get(Case, case_id)
    if case is None:
        return None
    evidence_case_id = case.evidence_case_id or case.id
    if case.owner_id == user_id:
        level = (
            CaseAccessLevel.COPY_OWNER
            if case.case_kind == "investigation_copy"
            else CaseAccessLevel.OWNER
        )
        return CaseAccess(case=case, level=level, evidence_case_id=evidence_case_id)
    checked_at = now or datetime.now(UTC)
    grant = db.scalar(
        select(CaseAccessGrant).where(
            CaseAccessGrant.case_id == case_id,
            CaseAccessGrant.recipient_id == user_id,
            CaseAccessGrant.activated_at.is_not(None),
            CaseAccessGrant.revoked_at.is_(None),
            CaseAccessGrant.expires_at > checked_at,
        )
    )
    if grant is None:
        return None
    return CaseAccess(
        case=case,
        level=CaseAccessLevel.TEMPORARY_READ_ONLY,
        evidence_case_id=evidence_case_id,
        grant=grant,
    )


def require_case_view(db: Session, case_id: uuid.UUID, user_id: uuid.UUID) -> CaseAccess:
    access = resolve_case_access(db, case_id, user_id)
    if access is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return access


def require_case_modify(db: Session, case_id: uuid.UUID, user_id: uuid.UUID) -> CaseAccess:
    access = require_case_view(db, case_id, user_id)
    if not access.can_modify:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return access


def require_original_owner(db: Session, case_id: uuid.UUID, user_id: uuid.UUID) -> CaseAccess:
    access = require_case_view(db, case_id, user_id)
    if not access.is_original_owner or access.case.case_kind != "original":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return access
