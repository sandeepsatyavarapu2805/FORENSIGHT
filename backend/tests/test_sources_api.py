from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.evidence_source import EvidenceSource
from app.models.user import User
from tests.conftest import TEST_PASSWORD


def test_source_crud_inside_owned_case(
    authenticated_client: tuple[TestClient, User],
) -> None:
    client, _ = authenticated_client
    case_id = client.post("/cases", json={"name": "Source case"}).json()["id"]

    created = client.post(
        f"/cases/{case_id}/sources",
        json={"label": "Suspect phone", "description": "Sealed device"},
    )
    assert created.status_code == 201
    source_id = created.json()["id"]
    assert created.json()["case_id"] == case_id

    listed = client.get(f"/cases/{case_id}/sources")
    assert listed.status_code == 200
    assert [source["id"] for source in listed.json()] == [source_id]

    retrieved = client.get(f"/cases/{case_id}/sources/{source_id}")
    assert retrieved.status_code == 200
    assert retrieved.json()["label"] == "Suspect phone"

    updated = client.patch(
        f"/cases/{case_id}/sources/{source_id}",
        json={"label": "Primary handset", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "Primary handset"
    assert updated.json()["description"] is None


def test_source_access_is_scoped_through_case_owner(
    client: TestClient, db: Session, user_factory: Callable[..., User]
) -> None:
    owner = user_factory(username="source-owner")
    intruder = user_factory(username="source-intruder")
    case = Case(case_identifier="FS-PRIVATE-SOURCE", name="Private", owner_id=owner.id)
    db.add(case)
    db.flush()
    source = EvidenceSource(case_id=case.id, label="Private phone")
    db.add(source)
    db.commit()

    client.post(
        "/auth/login", json={"username": intruder.username, "password": TEST_PASSWORD}
    )
    base = f"/cases/{case.id}/sources"
    assert client.get(base).status_code == 404
    assert client.post(base, json={"label": "Injected"}).status_code == 404
    assert client.get(f"{base}/{source.id}").status_code == 404
    assert client.patch(f"{base}/{source.id}", json={"label": "Stolen"}).status_code == 404


def test_source_cannot_be_retrieved_through_a_different_case(
    authenticated_client: tuple[TestClient, User],
) -> None:
    client, _ = authenticated_client
    first_case = client.post("/cases", json={"name": "First"}).json()["id"]
    second_case = client.post("/cases", json={"name": "Second"}).json()["id"]
    source_id = client.post(
        f"/cases/{first_case}/sources", json={"label": "Phone"}
    ).json()["id"]

    assert client.get(f"/cases/{second_case}/sources/{source_id}").status_code == 404


def test_source_validation_and_invalid_ids(
    authenticated_client: tuple[TestClient, User],
) -> None:
    client, _ = authenticated_client
    case_id = client.post("/cases", json={"name": "Validation"}).json()["id"]
    assert client.post(f"/cases/{case_id}/sources", json={"label": " "}).status_code == 422
    assert client.get(f"/cases/{case_id}/sources/not-a-uuid").status_code == 422
    assert client.get("/cases/not-a-uuid/sources").status_code == 422


def test_source_patch_rejects_explicit_null_label(
    authenticated_client: tuple[TestClient, User],
) -> None:
    client, _ = authenticated_client
    case_id = client.post("/cases", json={"name": "Null validation"}).json()["id"]
    source_id = client.post(
        f"/cases/{case_id}/sources",
        json={"label": "Original label", "description": "Clear me"},
    ).json()["id"]

    response = client.patch(
        f"/cases/{case_id}/sources/{source_id}", json={"label": None}
    )

    assert response.status_code == 422
    assert (
        client.get(f"/cases/{case_id}/sources/{source_id}").json()["label"]
        == "Original label"
    )

    cleared = client.patch(
        f"/cases/{case_id}/sources/{source_id}", json={"description": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["label"] == "Original label"
    assert cleared.json()["description"] is None
