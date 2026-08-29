import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import require_case_view, require_original_owner
from app.api.cases import _new_case_identifier
from app.api.dependencies import get_current_user
from app.audit import audit_event
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.models.case import Case
from app.models.case_access_grant import CaseAccessGrant
from app.models.user import User
from app.schemas import (
    AccessibleCaseResponse,
    AuditEventResponse,
    CaseResponse,
    GrantActivate,
    GrantCreate,
    GrantCreatedResponse,
    GrantResponse,
    InvestigationCopyResponse,
)
from app.security import hash_session_token

router = APIRouter(tags=["case access"])


def _grant_status(grant: CaseAccessGrant, now: datetime | None = None) -> str:
    checked_at = now or datetime.now(UTC)
    if grant.revoked_at is not None:
        return "revoked"
    if grant.expires_at <= checked_at:
        return "expired"
    if grant.activated_at is not None:
        return "active"
    return "pending"


def _grant_response(db: Session, grant: CaseAccessGrant) -> GrantResponse:
    recipient = db.get(User, grant.recipient_id)
    assert recipient is not None
    return GrantResponse(
        id=grant.id,
        case_id=grant.case_id,
        recipient_id=grant.recipient_id,
        recipient_username=recipient.username,
        created_at=grant.created_at,
        expires_at=grant.expires_at,
        activated_at=grant.activated_at,
        revoked_at=grant.revoked_at,
        status=_grant_status(grant),
    )


@router.post("/cases/{case_id}/access-grants", response_model=GrantCreatedResponse, status_code=201)
def create_grant(
    case_id: uuid.UUID,
    payload: GrantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GrantCreatedResponse:
    require_original_owner(db, case_id, current_user.id)
    recipient = db.scalar(
        select(User).where(
            User.username == payload.recipient_username.strip().lower(),
            User.is_active.is_(True),
        )
    )
    if recipient is None or recipient.id == current_user.id:
        raise HTTPException(status_code=422, detail="Recipient is not available")
    code = secrets.token_urlsafe(32)
    grant = CaseAccessGrant(
        case_id=case_id,
        owner_id=current_user.id,
        recipient_id=recipient.id,
        code_hash=hash_session_token(code),
        expires_at=datetime.now(UTC) + timedelta(hours=payload.duration_hours),
    )
    db.add(grant)
    db.flush()
    audit_event(
        db, action="share_grant_create", success=True, user_id=current_user.id,
        case_id=case_id, target_type="case_access_grant", target_id=grant.id,
        metadata={"recipient_id": str(recipient.id), "duration_hours": payload.duration_hours},
    )
    db.commit()
    db.refresh(grant)
    base = _grant_response(db, grant)
    return GrantCreatedResponse(**base.model_dump(), access_code=code)


@router.get("/cases/{case_id}/access-grants", response_model=list[GrantResponse])
def list_grants(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[GrantResponse]:
    require_original_owner(db, case_id, current_user.id)
    grants = list(db.scalars(select(CaseAccessGrant).where(CaseAccessGrant.case_id == case_id).order_by(CaseAccessGrant.created_at.desc())))
    return [_grant_response(db, grant) for grant in grants]


@router.post("/cases/{case_id}/access-grants/{grant_id}/revoke", response_model=GrantResponse)
def revoke_grant(
    case_id: uuid.UUID,
    grant_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GrantResponse:
    require_original_owner(db, case_id, current_user.id)
    grant = db.scalar(select(CaseAccessGrant).where(CaseAccessGrant.id == grant_id, CaseAccessGrant.case_id == case_id))
    if grant is None:
        raise HTTPException(status_code=404, detail="Grant not found")
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(UTC)
    audit_event(db, action="share_grant_revoke", success=True, user_id=current_user.id, case_id=case_id, target_type="case_access_grant", target_id=grant.id)
    db.commit()
    db.refresh(grant)
    return _grant_response(db, grant)


@router.post("/access-grants/{grant_id}/activate", response_model=GrantResponse)
def activate_grant(
    grant_id: uuid.UUID,
    payload: GrantActivate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GrantResponse:
    grant = db.scalar(select(CaseAccessGrant).where(CaseAccessGrant.id == grant_id, CaseAccessGrant.recipient_id == current_user.id))
    if grant is None:
        raise HTTPException(status_code=404, detail="Grant not found")
    now = datetime.now(UTC)
    valid = grant.revoked_at is None and grant.expires_at > now and secrets.compare_digest(
        grant.code_hash, hash_session_token(payload.code)
    )
    if not valid:
        audit_event(db, action="share_grant_activate", success=False, user_id=current_user.id, case_id=grant.case_id, target_type="case_access_grant", target_id=grant.id)
        db.commit()
        raise HTTPException(status_code=403, detail="Grant activation failed")
    if grant.activated_at is None:
        grant.activated_at = now
    audit_event(db, action="share_grant_activate", success=True, user_id=current_user.id, case_id=grant.case_id, target_type="case_access_grant", target_id=grant.id)
    db.commit()
    db.refresh(grant)
    return _grant_response(db, grant)


@router.get("/access/shared-cases", response_model=list[AccessibleCaseResponse])
def list_shared_cases(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[AccessibleCaseResponse]:
    now = datetime.now(UTC)
    grants = list(db.scalars(select(CaseAccessGrant).where(
        CaseAccessGrant.recipient_id == current_user.id,
        CaseAccessGrant.activated_at.is_not(None),
        CaseAccessGrant.revoked_at.is_(None),
        CaseAccessGrant.expires_at > now,
    )))
    return [AccessibleCaseResponse(case=CaseResponse.model_validate(db.get(Case, grant.case_id)), grant_id=grant.id, access_level="temporary_read_only", expires_at=grant.expires_at) for grant in grants]


@router.post("/access-grants/{grant_id}/copy", response_model=InvestigationCopyResponse, status_code=201)
def create_investigation_copy(
    grant_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvestigationCopyResponse:
    grant = db.scalar(select(CaseAccessGrant).where(CaseAccessGrant.id == grant_id, CaseAccessGrant.recipient_id == current_user.id))
    if grant is None:
        raise HTTPException(status_code=404, detail="Grant not found")
    access = require_case_view(db, grant.case_id, current_user.id)
    if access.grant is None or access.grant.id != grant.id:
        raise HTTPException(status_code=404, detail="Grant not found")
    existing = db.scalar(select(Case).where(Case.source_grant_id == grant.id))
    if existing is not None:
        return InvestigationCopyResponse(case=existing, original_case=access.case)
    copy = Case(
        case_identifier=_new_case_identifier().replace("FS-", "FS-COPY-", 1),
        name=f"Investigation Copy — {access.case.name}",
        description="Independent investigation copy referencing immutable original evidence.",
        owner_id=current_user.id,
        case_kind="investigation_copy",
        parent_case_id=access.case.id,
        evidence_case_id=access.evidence_case_id,
        source_grant_id=grant.id,
    )
    db.add(copy)
    db.flush()
    audit_event(db, action="investigation_copy_create", success=True, user_id=current_user.id, case_id=copy.id, target_type="case", target_id=copy.id, metadata={"original_case_id": str(access.case.id)})
    db.commit()
    db.refresh(copy)
    return InvestigationCopyResponse(case=copy, original_case=access.case)


@router.get("/cases/{case_id}/audit", response_model=list[AuditEventResponse])
def list_case_audit(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AuditEvent]:
    require_original_owner(db, case_id, current_user.id)
    return list(db.scalars(select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.occurred_at.desc())))
