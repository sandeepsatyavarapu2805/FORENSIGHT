import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.finding import Finding
from app.models.finding_evidence import FindingEvidence
from app.models.user import User
from app.security import hash_password

LEGACY_DEMO_USERNAME = "demo-investigator"
LEGACY_DEMO_CASE_IDENTIFIER = "FS-DEMO-2025-001"


def _demo_case_identifier(user: User) -> str:
    """Return a stable globally unique-enough identifier for this demo owner."""
    if user.username.casefold() == LEGACY_DEMO_USERNAME:
        return LEGACY_DEMO_CASE_IDENTIFIER
    return f"FS-DEMO-{user.id.hex[:12].upper()}"


def seed_demo(db: Session, username: str, display_name: str, password: str | None) -> Case:
    username = username.strip().lower()
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        if password is None or len(password) < 12:
            raise ValueError("A password of at least 12 characters is required for a new user")
        user = User(
            username=username,
            display_name=display_name.strip(),
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()

    case_identifier = _demo_case_identifier(user)
    existing = db.scalar(
        select(Case).where(
            Case.case_identifier == case_identifier,
            Case.owner_id == user.id,
        )
    )
    if existing is not None:
        return existing

    case = Case(
        case_identifier=case_identifier,
        name="Synthetic Demonstration Investigation",
        description=(
            "Clearly fictional normalized evidence for demonstrating ForenSight. "
            "This is not a UFDR import and contains no real-person data."
        ),
        owner_id=user.id,
    )
    db.add(case)
    db.flush()

    manifest = b"forensight-synthetic-demo-v1"
    source = EvidenceSource(
        case_id=case.id,
        label="Synthetic Demo Device",
        description="Fictional test-only normalized evidence; not a real UFDR source.",
        original_filename="synthetic-demo-manifest.json",
        file_size=len(manifest),
        sha256=hashlib.sha256(manifest).hexdigest(),
        imported_by_id=user.id,
        imported_at=datetime.now(UTC),
        parser_identifier="demo.synthetic.normalized",
        parser_version="1.0",
        processing_state="ready",
        processing_stage="complete",
        evidence_count=6,
        evidence_counts={"message": 3, "call": 1, "contact": 1, "application": 1},
    )
    db.add(source)
    db.flush()

    occurred = datetime(2025, 8, 15, 9, 30, tzinfo=UTC)
    records = [
        ("MSG-DEMO-001", "message", "msg-001", "Asha asked Kabir to meet at the fictional North Station cafe.", "Signal Demo", [{"type": "person", "value": "Asha Rao"}, {"type": "person", "value": "Kabir Sen"}]),
        ("MSG-DEMO-002", "message", "msg-002", "Kabir shared fictional reference DEMO-WALLET-42 for the case exercise.", "Signal Demo", [{"type": "person", "value": "Kabir Sen"}, {"type": "identifier", "value": "DEMO-WALLET-42"}]),
        ("CALL-DEMO-001", "call", "call-001", "Fictional outgoing call from Asha to Kabir lasting 184 seconds.", "Phone", [{"type": "person", "value": "Asha Rao"}, {"type": "person", "value": "Kabir Sen"}]),
        ("CONTACT-DEMO-001", "contact", "contact-001", "Fictional contact card for Kabir Sen.", "Contacts", [{"type": "person", "value": "Kabir Sen"}]),
        ("APP-DEMO-001", "application", "app-001", "Synthetic application installation record for Signal Demo.", "System", [{"type": "application", "value": "Signal Demo"}]),
        ("MSG-DEMO-003", "message", "msg-003", "Asha confirmed the fictional meeting time as 14:00.", "Signal Demo", [{"type": "person", "value": "Asha Rao"}]),
    ]
    evidence_items: list[EvidenceItem] = []
    for index, (reference, artifact_type, record_id, text, application, entities) in enumerate(records):
        item = EvidenceItem(
            evidence_reference=f"{reference}-{uuid.uuid4().hex[:6].upper()}",
            case_id=case.id,
            source_id=source.id,
            artifact_type=artifact_type,
            original_record_id=record_id,
            occurred_at=occurred + timedelta(minutes=index * 18),
            application=application,
            searchable_text=text,
            data={"entities": entities, "demo": True},
            raw_metadata={"fixture": "synthetic-demo-v1"},
            parser_identifier="demo.synthetic.normalized",
            parser_version="1.0",
        )
        evidence_items.append(item)
        db.add(item)
    db.flush()

    finding = Finding(
        case_id=case.id,
        title="Fictional meeting coordination",
        description=(
            "Demo records show the fictional participants coordinating a meeting. "
            "This conclusion is supported only by the linked synthetic messages."
        ),
        status="confirmed",
        created_by_id=user.id,
    )
    db.add(finding)
    db.flush()
    db.add_all(
        FindingEvidence(finding_id=finding.id, evidence_id=item.id)
        for item in (evidence_items[0], evidence_items[5])
    )
    db.commit()
    db.refresh(case)
    return case
