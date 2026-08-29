import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.demo_seed import seed_demo
from app.models.case import Case
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.finding import Finding
from app.models.user import User


def test_demo_seed_is_labeled_synthetic_and_idempotent(db: Session) -> None:
    username = f"demo-seed-{uuid.uuid4().hex}"
    case = seed_demo(
        db,
        username=username,
        display_name="Demo Seed Investigator",
        password="Synthetic demo password!",
    )
    repeated = seed_demo(
        db,
        username=username,
        display_name="Demo Seed Investigator",
        password=None,
    )

    assert case.id == repeated.id
    assert case.case_identifier.startswith("FS-DEMO-")
    assert case.owner_id == db.scalar(
        select(User.id).where(User.username == username)
    )
    assert db.scalar(
        select(func.count()).select_from(Case).where(Case.owner_id == case.owner_id)
    ) == 1
    source = db.scalar(select(EvidenceSource).where(EvidenceSource.case_id == case.id))
    assert source is not None
    assert source.label == "Synthetic Demo Device"
    assert source.description is not None
    assert "not a real UFDR source" in source.description
    assert source.parser_identifier == "demo.synthetic.normalized"
    assert db.scalar(
        select(func.count()).select_from(EvidenceItem).where(EvidenceItem.case_id == case.id)
    ) == 6
    assert db.scalar(
        select(func.count()).select_from(Finding).where(Finding.case_id == case.id)
    ) == 1


def test_different_investigators_receive_distinct_demo_cases(db: Session) -> None:
    first_username = f"demo-first-{uuid.uuid4().hex}"
    second_username = f"demo-second-{uuid.uuid4().hex}"

    first = seed_demo(
        db,
        username=first_username,
        display_name="First Demo Investigator",
        password="Synthetic demo password!",
    )
    second = seed_demo(
        db,
        username=second_username,
        display_name="Second Demo Investigator",
        password="Synthetic demo password!",
    )

    assert first.id != second.id
    assert first.case_identifier != second.case_identifier
    assert first.owner_id != second.owner_id
    assert first.owner_id == db.scalar(
        select(User.id).where(User.username == first_username)
    )
    assert second.owner_id == db.scalar(
        select(User.id).where(User.username == second_username)
    )
    assert db.scalar(
        select(func.count()).select_from(EvidenceItem).where(
            EvidenceItem.case_id.in_([first.id, second.id])
        )
    ) == 12
