import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.user import User
from tests.conftest import TEST_PASSWORD


def create_analysis_case(
    db: Session,
    owner: User,
    *,
    partial: bool = False,
) -> tuple[Case, EvidenceSource, list[EvidenceItem]]:
    case = Case(
        case_identifier=f"FS-AN-{uuid.uuid4().hex[:8]}",
        name="Analysis Case",
        owner_id=owner.id,
    )
    db.add(case)
    db.flush()

    source = EvidenceSource(
        case_id=case.id,
        label="Analysis Device",
        is_partial=partial,
    )
    db.add(source)
    db.flush()

    now = datetime.now(UTC)

    items = [
        EvidenceItem(
            evidence_reference=f"MSG-{uuid.uuid4().hex[:12].upper()}",
            case_id=case.id,
            source_id=source.id,
            artifact_type="message",
            original_record_id="msg-1",
            occurred_at=now - timedelta(hours=2),
            application="ChatApp",
            searchable_text="Conversation involving Alice and Bob",
            data={
                "entities": [
                    {"type": "person", "value": "Alice"},
                    {"type": "person", "value": "Bob"},
                ]
            },
            raw_metadata={},
            parser_identifier="test.fixture",
            parser_version="1",
        ),
        EvidenceItem(
            evidence_reference=f"MSG-{uuid.uuid4().hex[:12].upper()}",
            case_id=case.id,
            source_id=source.id,
            artifact_type="message",
            original_record_id="msg-2",
            occurred_at=now - timedelta(hours=1),
            application="ChatApp",
            searchable_text="Second conversation involving Alice",
            data={
                "entities": [
                    {"type": "person", "value": "Alice"},
                ]
            },
            raw_metadata={},
            parser_identifier="test.fixture",
            parser_version="1",
        ),
        EvidenceItem(
            evidence_reference=f"CONTACT-{uuid.uuid4().hex[:12].upper()}",
            case_id=case.id,
            source_id=source.id,
            artifact_type="contact",
            original_record_id="contact-1",
            occurred_at=None,
            application="Contacts",
            searchable_text="Contact record",
            data={
                "entities": [
                    {"type": "person", "value": "Bob"},
                ]
            },
            raw_metadata={},
            parser_identifier="test.fixture",
            parser_version="1",
        ),
    ]

    db.add_all(items)
    db.commit()

    return case, source, items


def test_analysis_returns_grounded_entities_timeline_and_relationships(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client
    case, _, items = create_analysis_case(db, user)

    response = client.get(f"/cases/{case.id}/analysis")

    assert response.status_code == 200
    body = response.json()

    alice = next(
        entity
        for entity in body["entities"]
        if entity["key"] == "person:alice"
    )

    assert alice["value"] == "Alice"
    assert alice["occurrence_count"] == 2
    assert set(alice["evidence_ids"]) == {
        str(items[0].id),
        str(items[1].id),
    }

    chat_app = next(
        entity
        for entity in body["entities"]
        if entity["key"] == "application:chatapp"
    )
    assert chat_app["occurrence_count"] == 2

    assert len(body["timeline"]) == 2
    assert body["timeline"][0]["evidence_id"] == str(items[0].id)
    assert body["timeline"][1]["evidence_id"] == str(items[1].id)

    relationship = next(
        relation
        for relation in body["relationships"]
        if {
            relation["source_key"],
            relation["target_key"],
        }
        == {"person:alice", "person:bob"}
    )

    assert relationship["relationship_type"] == "co_occurrence"
    assert relationship["occurrence_count"] == 1
    assert relationship["evidence_ids"] == [str(items[0].id)]


def test_analysis_does_not_infer_entities_from_free_text(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client
    case, source, _ = create_analysis_case(db, user)

    item = EvidenceItem(
        evidence_reference=f"MSG-{uuid.uuid4().hex[:12].upper()}",
        case_id=case.id,
        source_id=source.id,
        artifact_type="message",
        original_record_id="free-text-only",
        searchable_text="Charlie called +911234567890",
        data={},
        raw_metadata={},
        parser_identifier="test.fixture",
        parser_version="1",
    )
    db.add(item)
    db.commit()

    response = client.get(f"/cases/{case.id}/analysis")

    assert response.status_code == 200

    values = {
        entity["value"]
        for entity in response.json()["entities"]
    }

    assert "Charlie" not in values
    assert "+911234567890" not in values


def test_analysis_reports_partial_source_warning(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client
    case, _, _ = create_analysis_case(
        db,
        user,
        partial=True,
    )

    response = client.get(f"/cases/{case.id}/analysis")

    assert response.status_code == 200
    assert response.json()["warnings"] == [
        "Analysis Device: Source partially parsed — continue with caution."
    ]


def test_analysis_empty_case_returns_empty_results(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client

    case = Case(
        case_identifier=f"FS-EMPTY-{uuid.uuid4().hex[:8]}",
        name="Empty Analysis",
        owner_id=user.id,
    )
    db.add(case)
    db.commit()

    response = client.get(f"/cases/{case.id}/analysis")

    assert response.status_code == 200
    assert response.json() == {
        "entities": [],
        "timeline": [],
        "relationships": [],
        "warnings": [],
    }


def test_analysis_preserves_case_isolation(
    client: TestClient,
    db: Session,
    user_factory: Callable[..., User],
) -> None:
    owner = user_factory(username="analysis-owner")
    intruder = user_factory(username="analysis-intruder")

    case, _, _ = create_analysis_case(db, owner)

    client.post(
        "/auth/login",
        json={
            "username": intruder.username,
            "password": TEST_PASSWORD,
        },
    )

    assert client.get(
        f"/cases/{case.id}/analysis"
    ).status_code == 404