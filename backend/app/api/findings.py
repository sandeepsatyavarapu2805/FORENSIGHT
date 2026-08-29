import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.cases import _owned_case
from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.evidence_item import EvidenceItem
from app.models.finding import Finding
from app.models.finding_evidence import FindingEvidence
from app.models.user import User
from app.schemas import (
    FindingCreate,
    FindingEvidenceAttach,
    FindingEvidenceResponse,
    FindingResponse,
    FindingUpdate,
)

router = APIRouter(prefix="/cases/{case_id}/findings", tags=["findings"])


def _finding_query(case_id: uuid.UUID):
    return (
        select(Finding)
        .where(Finding.case_id == case_id)
        .options(selectinload(Finding.evidence_links).selectinload(FindingEvidence.evidence))
    )


def _owned_finding(db: Session, case_id: uuid.UUID, finding_id: uuid.UUID) -> Finding:
    finding = db.scalar(_finding_query(case_id).where(Finding.id == finding_id))
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return finding


def _evidence_response(item: EvidenceItem) -> FindingEvidenceResponse:
    return FindingEvidenceResponse(
        id=item.id,
        evidence_reference=item.evidence_reference,
        source_id=item.source_id,
        artifact_type=item.artifact_type,
        application=item.application,
        occurred_at=item.occurred_at,
    )


def finding_response(finding: Finding) -> FindingResponse:
    return FindingResponse(
        id=finding.id,
        case_id=finding.case_id,
        title=finding.title,
        description=finding.description,
        status=finding.status,
        created_by_id=finding.created_by_id,
        created_at=finding.created_at,
        updated_at=finding.updated_at,
        evidence=[_evidence_response(link.evidence) for link in finding.evidence_links],
    )


def _case_evidence(db: Session, case_id: uuid.UUID, reference: str) -> EvidenceItem:
    item = db.scalar(
        select(EvidenceItem).where(
            EvidenceItem.case_id == case_id,
            func.lower(EvidenceItem.evidence_reference) == reference.strip().lower(),
        )
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Evidence reference does not belong to this case: {reference}",
        )
    return item


@router.post("", response_model=FindingResponse, status_code=status.HTTP_201_CREATED)
def create_finding(
    case_id: uuid.UUID,
    payload: FindingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FindingResponse:
    _owned_case(db, case_id, current_user.id)
    evidence = {
        item.id: item
        for item in (_case_evidence(db, case_id, reference) for reference in payload.evidence_references)
    }
    finding = Finding(
        case_id=case_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        created_by_id=current_user.id,
    )
    db.add(finding)
    db.flush()
    db.add_all(
        FindingEvidence(finding_id=finding.id, evidence_id=item.id)
        for item in evidence.values()
    )
    db.commit()
    return finding_response(_owned_finding(db, case_id, finding.id))


@router.get("", response_model=list[FindingResponse])
def list_findings(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FindingResponse]:
    _owned_case(db, case_id, current_user.id)
    findings = list(db.scalars(_finding_query(case_id).order_by(Finding.updated_at.desc())))
    return [finding_response(finding) for finding in findings]


@router.get("/{finding_id}", response_model=FindingResponse)
def get_finding(
    case_id: uuid.UUID,
    finding_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FindingResponse:
    _owned_case(db, case_id, current_user.id)
    return finding_response(_owned_finding(db, case_id, finding_id))


@router.patch("/{finding_id}", response_model=FindingResponse)
def update_finding(
    case_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: FindingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FindingResponse:
    _owned_case(db, case_id, current_user.id)
    finding = _owned_finding(db, case_id, finding_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(finding, field, value)
    db.commit()
    return finding_response(_owned_finding(db, case_id, finding_id))


@router.post("/{finding_id}/evidence", response_model=FindingResponse)
def attach_evidence(
    case_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: FindingEvidenceAttach,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FindingResponse:
    _owned_case(db, case_id, current_user.id)
    finding = _owned_finding(db, case_id, finding_id)
    item = _case_evidence(db, case_id, payload.evidence_reference)
    if not any(link.evidence_id == item.id for link in finding.evidence_links):
        db.add(FindingEvidence(finding_id=finding.id, evidence_id=item.id))
        db.commit()
        db.expire(finding, ["evidence_links"])
    return finding_response(_owned_finding(db, case_id, finding_id))


@router.delete("/{finding_id}/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_evidence(
    case_id: uuid.UUID,
    finding_id: uuid.UUID,
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _owned_case(db, case_id, current_user.id)
    _owned_finding(db, case_id, finding_id)
    link = db.get(FindingEvidence, (finding_id, evidence_id))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence link not found")
    db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
