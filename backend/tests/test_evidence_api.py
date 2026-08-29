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


def add_evidence(
    db: Session,
    case: Case,
    source: EvidenceSource,
    *,
    artifact_type: str,
    original_id: str,
    text: str,
    occurred_at: datetime | None,
    application: str | None = None,
) -> EvidenceItem:
    item = EvidenceItem(
        evidence_reference=f"EVID-{uuid.uuid4().hex[:12].upper()}",
        case_id=case.id,
        source_id=source.id,
        artifact_type=artifact_type,
        original_record_id=original_id,
        occurred_at=occurred_at,
        application=application,
        searchable_text=text,
        data={"display": text},
        raw_metadata={"source_key": original_id},
        parser_identifier="test.fixture",
        parser_version="1",
    )
    db.add(item)
    return item


def evidence_fixture(
    db: Session, owner: User
) -> tuple[Case, EvidenceSource, list[EvidenceItem]]:
    case = Case(
        case_identifier=f"FS-EVID-{uuid.uuid4().hex[:8]}",
        name="Evidence",
        owner_id=owner.id,
    )
    db.add(case)
    db.flush()
    source = EvidenceSource(case_id=case.id, label="Device")
    db.add(source)
    db.flush()
    now = datetime.now(UTC)
    items = [
    add_evidence(
        db,
        case,
        source,
        artifact_type="message",
        original_id="m1",
        text="alpha conversation 100% complete",
        occurred_at=now,
        application="ChatApp",
    ),
    add_evidence(
        db,
        case,
        source,
        artifact_type="message",
        original_id="m2",
        text="beta_conversation",
        occurred_at=now - timedelta(days=1),
        application="ChatApp",
    ),
    add_evidence(
            db,
            case,
            source,
            artifact_type="contact",
            original_id="c1",
            text="Alpha Person",
            occurred_at=None,
            application="Contacts",
        ),
    ]
    db.commit()
    return case, source, items


def test_evidence_page_paginates_and_filters_common_fields(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, source, _ = evidence_fixture(db, user)

    first = client.get(f"/cases/{case.id}/evidence", params={"limit": 2})
    assert first.status_code == 200
    assert first.json()["total"] == 3
    assert len(first.json()["items"]) == 2
    assert first.json()["offset"] == 0

    filtered = client.get(
        f"/cases/{case.id}/evidence",
        params={
            "artifact_type": "message",
            "source_id": str(source.id),
            "query": "beta",
        },
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["original_record_id"] == "m2"


def test_evidence_preview_preserves_generic_provenance_and_is_read_only(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, source, items = evidence_fixture(db, user)
    item = items[0]

    response = client.get(f"/cases/{case.id}/evidence/{item.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == str(case.id)
    assert body["source_id"] == str(source.id)
    assert body["original_record_id"] == "m1"
    assert body["raw_metadata"] == {"source_key": "m1"}
    assert (
        client.patch(
            f"/cases/{case.id}/evidence/{item.id}", json={"data": {}}
        ).status_code
        == 405
    )
    assert client.delete(f"/cases/{case.id}/evidence/{item.id}").status_code == 405


def test_evidence_isolation_denies_other_investigators(
    client: TestClient,
    db: Session,
    user_factory: Callable[..., User],
) -> None:
    owner = user_factory(username="evidence-owner")
    intruder = user_factory(username="evidence-intruder")
    case, _, items = evidence_fixture(db, owner)
    client.post(
        "/auth/login", json={"username": intruder.username, "password": TEST_PASSWORD}
    )

    assert client.get(f"/cases/{case.id}/evidence").status_code == 404
    assert client.get(f"/cases/{case.id}/evidence/{items[0].id}").status_code == 404

def test_evidence_lookup_by_reference(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, _, items = evidence_fixture(db, user)

    response = client.get(
        f"/cases/{case.id}/evidence/by-reference/{items[0].evidence_reference.lower()}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(items[0].id)
    assert response.json()["evidence_reference"] == items[0].evidence_reference


def test_evidence_filters_include_actual_types_and_applications(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, _, _ = evidence_fixture(db, user)

    response = client.get(f"/cases/{case.id}/evidence/filters")

    assert response.status_code == 200
    body = response.json()

    assert body["artifact_types"] == ["contact", "message"]
    assert body["applications"] == ["ChatApp", "Contacts"]


def test_evidence_can_filter_by_application(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, _, _ = evidence_fixture(db, user)

    response = client.get(
        f"/cases/{case.id}/evidence",
        params={"application": "chatapp"},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["total"] == 2
    assert all(item["application"] == "ChatApp" for item in body["items"])


def test_evidence_sort_supports_newest_and_oldest(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, _, _ = evidence_fixture(db, user)

    newest = client.get(
        f"/cases/{case.id}/evidence",
        params={"artifact_type": "message", "sort": "newest"},
    )
    oldest = client.get(
        f"/cases/{case.id}/evidence",
        params={"artifact_type": "message", "sort": "oldest"},
    )

    assert newest.status_code == 200
    assert oldest.status_code == 200

    assert newest.json()["items"][0]["original_record_id"] == "m1"
    assert oldest.json()["items"][0]["original_record_id"] == "m2"


def test_evidence_text_search_treats_like_wildcards_as_literals(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, _, _ = evidence_fixture(db, user)

    percent = client.get(
        f"/cases/{case.id}/evidence",
        params={"query": "100%"},
    )
    underscore = client.get(
        f"/cases/{case.id}/evidence",
        params={"query": "beta_conversation"},
    )

    assert percent.status_code == 200
    assert percent.json()["total"] == 1
    assert percent.json()["items"][0]["original_record_id"] == "m1"

    assert underscore.status_code == 200
    assert underscore.json()["total"] == 1
    assert underscore.json()["items"][0]["original_record_id"] == "m2"


def test_evidence_rejects_invalid_date_range(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    case, _, _ = evidence_fixture(db, user)

    response = client.get(
        f"/cases/{case.id}/evidence",
        params={
            "date_from": "2026-08-30T00:00:00Z",
            "date_to": "2026-08-29T00:00:00Z",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "date_from must not be later than date_to"


def test_evidence_filter_and_reference_endpoints_preserve_case_isolation(
    client: TestClient,
    db: Session,
    user_factory: Callable[..., User],
) -> None:
    owner = user_factory(username="evidence-filter-owner")
    intruder = user_factory(username="evidence-filter-intruder")
    case, _, items = evidence_fixture(db, owner)

    client.post(
        "/auth/login",
        json={"username": intruder.username, "password": TEST_PASSWORD},
    )

    assert client.get(f"/cases/{case.id}/evidence/filters").status_code == 404

    assert client.get(
        f"/cases/{case.id}/evidence/by-reference/{items[0].evidence_reference}"
    ).status_code == 404