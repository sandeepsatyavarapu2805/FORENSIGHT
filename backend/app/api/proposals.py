import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.access import require_case_modify, require_original_owner
from app.api.dependencies import get_current_user
from app.api.findings import _evidence_response
from app.audit import audit_event
from app.db.session import get_db
from app.models.evidence_item import EvidenceItem
from app.models.finding import Finding
from app.models.finding_evidence import FindingEvidence
from app.models.proposed_finding import ProposedFinding, ProposedFindingEvidence
from app.models.user import User
from app.schemas import ProposedFindingCreate, ProposedFindingResponse, ProposedFindingUpdate

router = APIRouter(tags=["proposed findings"])


def _proposal_query():
    return select(ProposedFinding).options(
        selectinload(ProposedFinding.evidence_links).selectinload(ProposedFindingEvidence.evidence)
    )


def _proposal_response(proposal: ProposedFinding) -> ProposedFindingResponse:
    return ProposedFindingResponse(
        id=proposal.id,
        source_copy_case_id=proposal.source_copy_case_id,
        original_case_id=proposal.original_case_id,
        submitted_by_id=proposal.submitted_by_id,
        title=proposal.title,
        description=proposal.description,
        status=proposal.status,
        evidence=[_evidence_response(link.evidence) for link in proposal.evidence_links],
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        submitted_at=proposal.submitted_at,
        reviewed_at=proposal.reviewed_at,
        reviewed_by_id=proposal.reviewed_by_id,
        accepted_finding_id=proposal.accepted_finding_id,
    )


def _copy_access(db: Session, copy_case_id: uuid.UUID, user_id: uuid.UUID):
    access = require_case_modify(db, copy_case_id, user_id)
    if access.case.case_kind != "investigation_copy" or access.case.parent_case_id is None:
        raise HTTPException(status_code=404, detail="Investigation copy not found")
    return access


def _evidence_for_references(db: Session, evidence_case_id: uuid.UUID, references: list[str]) -> dict[uuid.UUID, EvidenceItem]:
    items: dict[uuid.UUID, EvidenceItem] = {}
    for reference in references:
        item = db.scalar(select(EvidenceItem).where(
            EvidenceItem.case_id == evidence_case_id,
            func.lower(EvidenceItem.evidence_reference) == reference.strip().lower(),
        ))
        if item is None:
            raise HTTPException(status_code=422, detail=f"Evidence reference does not belong to this investigation: {reference}")
        items[item.id] = item
    return items


@router.post("/cases/{copy_case_id}/proposals", response_model=ProposedFindingResponse, status_code=201)
def create_proposal(
    copy_case_id: uuid.UUID,
    payload: ProposedFindingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposedFindingResponse:
    access = _copy_access(db, copy_case_id, current_user.id)
    evidence = _evidence_for_references(db, access.evidence_case_id, payload.evidence_references)
    proposal = ProposedFinding(
        source_copy_case_id=copy_case_id,
        original_case_id=access.case.parent_case_id,
        submitted_by_id=current_user.id,
        title=payload.title,
        description=payload.description,
    )
    db.add(proposal)
    db.flush()
    db.add_all(ProposedFindingEvidence(proposal_id=proposal.id, evidence_id=item.id) for item in evidence.values())
    audit_event(db, action="proposal_create", success=True, user_id=current_user.id, case_id=copy_case_id, target_type="proposed_finding", target_id=proposal.id)
    db.commit()
    return _proposal_response(db.scalar(_proposal_query().where(ProposedFinding.id == proposal.id)))


@router.get("/cases/{case_id}/proposals", response_model=list[ProposedFindingResponse])
def list_proposals(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProposedFindingResponse]:
    access = require_case_modify(db, case_id, current_user.id)
    if access.case.case_kind == "investigation_copy":
        condition = ProposedFinding.source_copy_case_id == case_id
    else:
        require_original_owner(db, case_id, current_user.id)
        condition = ProposedFinding.original_case_id == case_id
    proposals = list(db.scalars(_proposal_query().where(condition).order_by(ProposedFinding.created_at.desc())))
    return [_proposal_response(proposal) for proposal in proposals]


def _owned_draft(db: Session, copy_case_id: uuid.UUID, proposal_id: uuid.UUID, user_id: uuid.UUID) -> ProposedFinding:
    _copy_access(db, copy_case_id, user_id)
    proposal = db.scalar(_proposal_query().where(
        ProposedFinding.id == proposal_id,
        ProposedFinding.source_copy_case_id == copy_case_id,
        ProposedFinding.submitted_by_id == user_id,
    ))
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


@router.patch("/cases/{copy_case_id}/proposals/{proposal_id}", response_model=ProposedFindingResponse)
def update_proposal(
    copy_case_id: uuid.UUID,
    proposal_id: uuid.UUID,
    payload: ProposedFindingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposedFindingResponse:
    proposal = _owned_draft(db, copy_case_id, proposal_id, current_user.id)
    if proposal.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft proposals can be edited")
    values = payload.model_dump(exclude_unset=True)
    references = values.pop("evidence_references", None)
    for field, value in values.items():
        if value is None:
            raise HTTPException(status_code=422, detail=f"{field} must not be null")
        setattr(proposal, field, value.strip() if isinstance(value, str) else value)
    if references is not None:
        access = _copy_access(db, copy_case_id, current_user.id)
        evidence = _evidence_for_references(db, access.evidence_case_id, references)
        proposal.evidence_links.clear()
        proposal.evidence_links.extend(ProposedFindingEvidence(evidence_id=item.id) for item in evidence.values())
    audit_event(db, action="proposal_update", success=True, user_id=current_user.id, case_id=copy_case_id, target_type="proposed_finding", target_id=proposal.id)
    db.commit()
    return _proposal_response(db.scalar(_proposal_query().where(ProposedFinding.id == proposal.id)))


@router.post("/cases/{copy_case_id}/proposals/{proposal_id}/submit", response_model=ProposedFindingResponse)
def submit_proposal(
    copy_case_id: uuid.UUID,
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProposedFindingResponse:
    proposal = _owned_draft(db, copy_case_id, proposal_id, current_user.id)
    if proposal.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft proposals can be submitted")
    proposal.status = "submitted"
    proposal.submitted_at = datetime.now(UTC)
    audit_event(db, action="proposal_submit", success=True, user_id=current_user.id, case_id=copy_case_id, target_type="proposed_finding", target_id=proposal.id)
    db.commit()
    return _proposal_response(db.scalar(_proposal_query().where(ProposedFinding.id == proposal.id)))


def _review_proposal(db: Session, original_case_id: uuid.UUID, proposal_id: uuid.UUID, user: User, decision: str) -> ProposedFindingResponse:
    require_original_owner(db, original_case_id, user.id)
    proposal = db.scalar(_proposal_query().where(ProposedFinding.id == proposal_id, ProposedFinding.original_case_id == original_case_id))
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "submitted":
        raise HTTPException(status_code=409, detail="Only submitted proposals can be reviewed")
    proposal.status = decision
    proposal.reviewed_at = datetime.now(UTC)
    proposal.reviewed_by_id = user.id
    if decision == "accepted":
        finding = Finding(
            case_id=original_case_id,
            title=proposal.title,
            description=proposal.description,
            status="draft",
            created_by_id=user.id,
            origin_proposal_id=proposal.id,
        )
        db.add(finding)
        db.flush()
        db.add_all(FindingEvidence(finding_id=finding.id, evidence_id=link.evidence_id) for link in proposal.evidence_links)
        proposal.accepted_finding_id = finding.id
    audit_event(db, action=f"proposal_{decision}", success=True, user_id=user.id, case_id=original_case_id, target_type="proposed_finding", target_id=proposal.id)
    db.commit()
    return _proposal_response(db.scalar(_proposal_query().where(ProposedFinding.id == proposal.id)))


@router.post("/cases/{original_case_id}/proposals/{proposal_id}/accept", response_model=ProposedFindingResponse)
def accept_proposal(original_case_id: uuid.UUID, proposal_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ProposedFindingResponse:
    return _review_proposal(db, original_case_id, proposal_id, current_user, "accepted")


@router.post("/cases/{original_case_id}/proposals/{proposal_id}/reject", response_model=ProposedFindingResponse)
def reject_proposal(original_case_id: uuid.UUID, proposal_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ProposedFindingResponse:
    return _review_proposal(db, original_case_id, proposal_id, current_user, "rejected")
