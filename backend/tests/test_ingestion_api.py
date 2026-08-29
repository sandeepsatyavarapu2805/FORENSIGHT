import hashlib
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.registry import ParserRegistry, get_parser_registry
from app.ingestion.storage import LocalFileStorage, get_file_storage
from app.main import app
from app.models.case import Case
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.user import User
from tests.conftest import TEST_PASSWORD
from tests.synthetic_parser import SyntheticParserAdapter


@pytest.fixture
def ingestion_storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "forensic-storage")


@pytest.fixture
def ingestion_client(
    client: TestClient, ingestion_storage: LocalFileStorage
) -> Generator[TestClient, None, None]:
    registry = ParserRegistry([SyntheticParserAdapter()])
    app.dependency_overrides[get_parser_registry] = lambda: registry
    app.dependency_overrides[get_file_storage] = lambda: ingestion_storage
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_parser_registry, None)
        app.dependency_overrides.pop(get_file_storage, None)


def create_case_and_source(client: TestClient) -> tuple[str, str]:
    case_id = client.post("/cases", json={"name": "Ingestion case"}).json()["id"]
    source_id = client.post(
        f"/cases/{case_id}/sources", json={"label": "Test device"}
    ).json()["id"]
    return case_id, source_id


def upload_path(case_id: str, source_id: str) -> str:
    return f"/cases/{case_id}/sources/{source_id}/upload"


def test_upload_requires_authentication(
    ingestion_client: TestClient,
) -> None:
    response = ingestion_client.post(
        f"/cases/00000000-0000-0000-0000-000000000001/sources/"
        "00000000-0000-0000-0000-000000000002/upload",
        files={"file": ("source.synthetic", b"VALID\n")},
    )
    assert response.status_code == 401


def test_valid_upload_records_integrity_and_uses_generated_storage_name(
    authenticated_client: tuple[TestClient, User],
    ingestion_client: TestClient,
    ingestion_storage: LocalFileStorage,
) -> None:
    client, user = authenticated_client
    case_id, source_id = create_case_and_source(client)
    content = b"VALID\nforensic fixture bytes"

    response = client.post(
        upload_path(case_id, source_id),
        files={"file": ("../../phone.synthetic", content, "application/octet-stream")},
    )

    assert response.status_code == 201
    source = response.json()
    assert source["original_filename"] == "phone.synthetic"
    assert source["file_size"] == len(content)
    assert source["sha256"] == hashlib.sha256(content).hexdigest()
    assert source["imported_by_id"] == str(user.id)
    assert source["parser_identifier"] == "test.synthetic"
    assert source["processing_state"] == "validated"
    stored_files = list(ingestion_storage.root.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].parent == ingestion_storage.root
    assert stored_files[0].name != "phone.synthetic"
    assert stored_files[0].read_bytes() == content


def test_unsupported_malformed_and_oversized_uploads_are_rejected_and_cleaned(
    authenticated_client: tuple[TestClient, User],
    ingestion_client: TestClient,
    ingestion_storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = authenticated_client
    case_id, source_id = create_case_and_source(client)

    unsupported = client.post(
        upload_path(case_id, source_id), files={"file": ("unknown.zip", b"data")}
    )
    assert unsupported.status_code == 415

    malformed = client.post(
        upload_path(case_id, source_id),
        files={"file": ("bad.synthetic", b"NOT_VALID\n")},
    )
    assert malformed.status_code == 422
    assert "invalid marker" in malformed.json()["detail"]
    assert list(ingestion_storage.root.iterdir()) == []

    monkeypatch.setattr(settings, "upload_max_bytes", 4)
    oversized = client.post(
        upload_path(case_id, source_id),
        files={"file": ("large.synthetic", b"VALID\n")},
    )
    assert oversized.status_code == 413
    assert list(ingestion_storage.root.iterdir()) == []


def test_ready_processing_normalizes_immutable_evidence_with_provenance(
    authenticated_client: tuple[TestClient, User],
    ingestion_client: TestClient,
    db: Session,
) -> None:
    client, _ = authenticated_client
    case_id, source_id = create_case_and_source(client)
    client.post(
        upload_path(case_id, source_id),
        files={"file": ("phone.synthetic", b"VALID\n")},
    )

    processed = client.post(f"/cases/{case_id}/sources/{source_id}/process")

    assert processed.status_code == 200
    job = processed.json()
    assert job["status"] == "ready"
    assert job["progress"] == 100
    assert job["stage_history"] == [
        "parsing",
        "normalization",
        "evidence_organization",
        "indexing",
    ]
    source = client.get(f"/cases/{case_id}/sources/{source_id}").json()
    assert source["processing_state"] == "ready"
    assert source["evidence_count"] == 2
    assert source["evidence_counts"] == {"message": 1, "contact": 1}

    evidence = client.get(
        f"/cases/{case_id}/sources/{source_id}/evidence"
    ).json()
    assert len(evidence) == 2
    assert {item["artifact_type"] for item in evidence} == {"message", "contact"}
    assert all(item["case_id"] == case_id for item in evidence)
    assert all(item["source_id"] == source_id for item in evidence)
    assert all(item["parser_identifier"] == "test.synthetic" for item in evidence)
    assert db.scalar(select(EvidenceItem)) is not None

    evidence_id = evidence[0]["id"]
    assert client.patch(f"/evidence/{evidence_id}", json={"data": {}}).status_code in {404, 405}
    assert client.delete(f"/evidence/{evidence_id}").status_code in {404, 405}
    assert client.post(f"/cases/{case_id}/sources/{source_id}/process").status_code == 409


def test_partial_and_fatal_processing_states(
    authenticated_client: tuple[TestClient, User],
    ingestion_client: TestClient,
) -> None:
    client, _ = authenticated_client
    partial_case, partial_source = create_case_and_source(client)
    client.post(
        upload_path(partial_case, partial_source),
        files={"file": ("partial.synthetic", b"PARTIAL\n")},
    )
    partial = client.post(
        f"/cases/{partial_case}/sources/{partial_source}/process"
    ).json()
    assert partial["status"] == "partially_processed"
    assert partial["diagnostics"][0]["code"] == "synthetic_bad_record"
    partial_source_body = client.get(
        f"/cases/{partial_case}/sources/{partial_source}"
    ).json()
    assert partial_source_body["is_partial"] is True
    assert partial_source_body["evidence_count"] == 1
    assert (
        partial_source_body["error_summary"]
        == "Source partially parsed — continue with caution."
    )

    fatal_case, fatal_source = create_case_and_source(client)
    client.post(
        upload_path(fatal_case, fatal_source),
        files={"file": ("fatal.synthetic", b"FATAL\n")},
    )
    fatal = client.post(f"/cases/{fatal_case}/sources/{fatal_source}/process").json()
    assert fatal["status"] == "failed"
    assert fatal["error_summary"] == "Synthetic fatal format error"
    assert client.get(f"/cases/{fatal_case}/sources/{fatal_source}/evidence").json() == []


def test_cross_investigator_ingestion_and_status_access_is_denied(
    client: TestClient,
    db: Session,
    user_factory: Callable[..., User],
    ingestion_client: TestClient,
) -> None:
    owner = user_factory(username="ingestion-owner")
    intruder = user_factory(username="ingestion-intruder")
    case = Case(case_identifier="FS-INGEST-PRIVATE", name="Private", owner_id=owner.id)
    db.add(case)
    db.flush()
    source = EvidenceSource(case_id=case.id, label="Private source")
    db.add(source)
    db.commit()

    assert client.post(
        "/auth/login", json={"username": intruder.username, "password": TEST_PASSWORD}
    ).status_code == 200
    base = f"/cases/{case.id}/sources/{source.id}"
    assert client.post(
        f"{base}/upload", files={"file": ("private.synthetic", b"VALID\n")}
    ).status_code == 404
    assert client.post(f"{base}/process").status_code == 404
    assert client.get(f"{base}/processing").status_code == 404
    assert client.get(f"{base}/evidence").status_code == 404
