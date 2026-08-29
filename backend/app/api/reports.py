import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.access import require_case_modify, require_case_view
from app.api.dependencies import get_current_auth_session, get_current_user
from app.api.findings import finding_response
from app.db.session import get_db
from app.audit import audit_event
from app.models.auth_session import AuthSession
from app.models.evidence_source import EvidenceSource
from app.models.finding import Finding
from app.models.finding_evidence import FindingEvidence
from app.models.user import User
from app.schemas import InvestigationReportResponse, PrintAuthorizationResponse, ReportSourceResponse

router = APIRouter(prefix="/cases/{case_id}/report", tags=["reports"])


@router.get("", response_model=InvestigationReportResponse)
def generate_report(
    case_id: uuid.UUID,
    finding_ids: list[uuid.UUID] | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvestigationReportResponse:
    access = require_case_view(db, case_id, current_user.id)
    case = access.case
    query = (
        select(Finding)
        .where(Finding.case_id == case_id)
        .options(selectinload(Finding.evidence_links).selectinload(FindingEvidence.evidence))
        .order_by(Finding.created_at)
    )
    if finding_ids is not None:
        query = query.where(Finding.id.in_(finding_ids))
    findings = list(db.scalars(query))
    source_ids = {
        link.evidence.source_id for finding in findings for link in finding.evidence_links
    }
    sources = list(
        db.scalars(
            select(EvidenceSource)
            .where(EvidenceSource.case_id == access.evidence_case_id, EvidenceSource.id.in_(source_ids))
            .order_by(EvidenceSource.label)
        )
    ) if source_ids else []
    warnings = [
        f"{source.label}: Source partially parsed — continue with caution."
        for source in sources
        if source.is_partial
    ]
    return InvestigationReportResponse(
        case=case,
        investigator=current_user,
        generated_at=datetime.now(UTC),
        findings=[finding_response(finding) for finding in findings],
        sources=[
            ReportSourceResponse(
                id=source.id,
                label=source.label,
                sha256=source.sha256,
                parser_identifier=source.parser_identifier,
                parser_version=source.parser_version,
                is_partial=source.is_partial,
            )
            for source in sources
        ],
        warnings=warnings,
    )


@router.post("/print-authorize", response_model=PrintAuthorizationResponse)
def authorize_report_print(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    auth_session: AuthSession = Depends(get_current_auth_session),
) -> PrintAuthorizationResponse:
    require_case_modify(db, case_id, current_user.id)
    now = datetime.now(UTC)
    authorized = (
        auth_session.user_id == current_user.id
        and auth_session.reauthenticated_until is not None
        and auth_session.reauthenticated_until > now
    )
    audit_event(
        db, action="report_print_authorize", success=authorized,
        user_id=current_user.id, case_id=case_id, target_type="report",
    )
    db.commit()
    if not authorized:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Fresh password reauthentication required")
    return PrintAuthorizationResponse(authorized=True, authorized_at=now)
