import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.user import User
from tests.conftest import TEST_PASSWORD


def create_case_evidence(
    db: Session, owner: User, *, partial: bool = False
) -> tuple[Case, EvidenceSource, EvidenceItem]:
    case = Case(
        case_identifier=f"FS-FIND-{uuid.uuid4().hex[:8]}",
        name="Findings Case",
        owner_id=owner.id,
    )
    db.add(case)
    db.flush()
    source = EvidenceSource(
        case_id=case.id,
        label="Device A",
        sha256="a" * 64,
        parser_identifier="test.fixture",
        parser_version="1",
        is_partial=partial,
    )
    db.add(source)
    db.flush()
    item = EvidenceItem(
        evidence_reference=f"MSG-{uuid.uuid4().hex[:12].upper()}",
        case_id=case.id,
        source_id=source.id,
        artifact_type="message",
        original_record_id="record-1",
        searchable_text="Grounded finding support",
        data={},
        raw_metadata={},
        parser_identifier="test.fixture",
        parser_version="1",
    )
    db.add(item)
    db.commit()
    return case, source, item


def test_finding_crud_and_evidence_links(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, _, item = create_case_evidence(db, user)
    created = client.post(
        f"/cases/{case.id}/findings",
        json={"title": "Wallet indicator", "description": "Supported claim"},
    )
    assert created.status_code == 201
    finding_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    attached = client.post(
        f"/cases/{case.id}/findings/{finding_id}/evidence",
        json={"evidence_reference": item.evidence_reference},
    )
    assert attached.status_code == 200
    assert attached.json()["evidence"][0]["evidence_reference"] == item.evidence_reference

    updated = client.patch(
        f"/cases/{case.id}/findings/{finding_id}",
        json={"status": "confirmed", "title": "Confirmed wallet indicator"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "confirmed"
    assert len(client.get(f"/cases/{case.id}/findings").json()) == 1

    detached = client.delete(
        f"/cases/{case.id}/findings/{finding_id}/evidence/{item.id}"
    )
    assert detached.status_code == 204
    assert client.get(f"/cases/{case.id}/findings/{finding_id}").json()["evidence"] == []


def test_finding_rejects_cross_case_evidence(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, _, _ = create_case_evidence(db, user)
    _, _, other_item = create_case_evidence(db, user)
    response = client.post(
        f"/cases/{case.id}/findings",
        json={"title": "Invalid", "evidence_references": [other_item.evidence_reference]},
    )
    assert response.status_code == 422


def test_finding_preserves_case_isolation(
    client: TestClient, db: Session, user_factory: Callable[..., User]
) -> None:
    owner = user_factory(username="finding-owner")
    intruder = user_factory(username="finding-intruder")
    case, _, _ = create_case_evidence(db, owner)
    client.post(
        "/auth/login",
        json={"username": intruder.username, "password": TEST_PASSWORD},
    )
    assert client.get(f"/cases/{case.id}/findings").status_code == 404


def test_report_is_deterministic_and_includes_provenance_warning(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, source, item = create_case_evidence(db, user, partial=True)
    finding = client.post(
        f"/cases/{case.id}/findings",
        json={
            "title": "Supported conclusion",
            "status": "confirmed",
            "evidence_references": [item.evidence_reference],
        },
    ).json()

    response = client.get(f"/cases/{case.id}/report")
    assert response.status_code == 200
    body = response.json()
    assert body["case"]["case_identifier"] == case.case_identifier
    assert body["investigator"]["username"] == user.username
    assert body["findings"][0]["id"] == finding["id"]
    assert body["sources"][0]["id"] == str(source.id)
    assert body["sources"][0]["sha256"] == "a" * 64
    assert body["warnings"] == [
        "Device A: Source partially parsed — continue with caution."
    ]
