from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.user import User
from tests.conftest import TEST_PASSWORD


def test_case_crud_for_owner(
    authenticated_client: tuple[TestClient, User], db: Session
) -> None:
    client, user = authenticated_client
    created = client.post(
        "/cases", json={"name": "Operation Dawn", "description": "Initial notes"}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["owner_id"] == str(user.id)
    assert body["case_identifier"].startswith("FS-")
    case_id = body["id"]
    assert db.get(Case, case_id) is not None

    listed = client.get("/cases")
    assert listed.status_code == 200
    assert [case["id"] for case in listed.json()] == [case_id]

    retrieved = client.get(f"/cases/{case_id}")
    assert retrieved.status_code == 200
    assert retrieved.json()["name"] == "Operation Dawn"

    updated = client.patch(
        f"/cases/{case_id}",
        json={"name": "Operation Sunrise", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Operation Sunrise"
    assert updated.json()["description"] is None


def test_case_access_is_scoped_to_owner(
    client: TestClient, db: Session, user_factory: Callable[..., User]
) -> None:
    owner = user_factory(username="owner")
    intruder = user_factory(username="intruder")
    case = Case(
        case_identifier="FS-PRIVATE-1", name="Private", owner_id=owner.id
    )
    db.add(case)
    db.commit()

    login = client.post(
        "/auth/login", json={"username": intruder.username, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200
    assert client.get(f"/cases/{case.id}").status_code == 404
    assert client.patch(f"/cases/{case.id}", json={"name": "Stolen"}).status_code == 404
    assert client.get("/cases").json() == []


def test_case_validation_and_invalid_id(
    authenticated_client: tuple[TestClient, User],
) -> None:
    client, _ = authenticated_client
    assert client.post("/cases", json={"name": "   "}).status_code == 422
    assert client.get("/cases/not-a-uuid").status_code == 422


def test_case_patch_rejects_explicit_null_name(
    authenticated_client: tuple[TestClient, User],
) -> None:
    client, _ = authenticated_client
    case_id = client.post(
        "/cases", json={"name": "Original name", "description": "Clear me"}
    ).json()["id"]

    response = client.patch(f"/cases/{case_id}", json={"name": None})

    assert response.status_code == 422
    assert client.get(f"/cases/{case_id}").json()["name"] == "Original name"

    cleared = client.patch(f"/cases/{case_id}", json={"description": None})
    assert cleared.status_code == 200
    assert cleared.json()["name"] == "Original name"
    assert cleared.json()["description"] is None
