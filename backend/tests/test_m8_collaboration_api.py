import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.access import CaseAccessLevel, resolve_case_access
from app.models.audit_event import AuditEvent
from app.models.auth_session import AuthSession
from app.models.case import Case
from app.models.case_access_grant import CaseAccessGrant
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.finding import Finding
from app.models.user import User
from tests.conftest import TEST_PASSWORD


def login(client: TestClient, user: User) -> None:
    response = client.post("/auth/login", json={"username": user.username, "password": TEST_PASSWORD})
    assert response.status_code == 200


def create_original(db: Session, owner: User) -> tuple[Case, EvidenceItem]:
    case = Case(
        case_identifier=f"FS-M8-{uuid.uuid4().hex[:10]}",
        name="M8 Original Case",
        owner_id=owner.id,
    )
    db.add(case)
    db.flush()
    source = EvidenceSource(case_id=case.id, label="M8 Device", processing_state="ready")
    db.add(source)
    db.flush()
    evidence = EvidenceItem(
        evidence_reference=f"MSG-M8-{uuid.uuid4().hex[:10].upper()}",
        case_id=case.id,
        source_id=source.id,
        artifact_type="message",
        original_record_id="m8-record-1",
        searchable_text="Fictional collaboration evidence with explicit wallet marker",
        data={"entities": [{"type": "identifier", "value": "M8-DEMO"}]},
        raw_metadata={},
        parser_identifier="test.fixture",
        parser_version="1",
    )
    db.add(evidence)
    db.commit()
    return case, evidence


def create_grant(client: TestClient, case: Case, recipient: User) -> dict[str, object]:
    response = client.post(
        f"/cases/{case.id}/access-grants",
        json={"recipient_username": recipient.username, "duration_hours": 24},
    )
    assert response.status_code == 201
    return response.json()


def test_access_resolver_requires_activation_and_enforces_expiry(
    db: Session, user_factory: Callable[..., User]
) -> None:
    owner = user_factory(username=f"owner-{uuid.uuid4().hex}")
    recipient = user_factory(username=f"recipient-{uuid.uuid4().hex}")
    case, _ = create_original(db, owner)
    grant = CaseAccessGrant(
        case_id=case.id,
        owner_id=owner.id,
        recipient_id=recipient.id,
        code_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(grant)
    db.commit()

    assert resolve_case_access(db, case.id, recipient.id) is None
    grant.activated_at = datetime.now(UTC)
    db.commit()
    access = resolve_case_access(db, case.id, recipient.id)
    assert access is not None
    assert access.level == CaseAccessLevel.TEMPORARY_READ_ONLY
    grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert resolve_case_access(db, case.id, recipient.id) is None


def test_share_activation_read_only_copy_and_proposal_workflow(
    client: TestClient,
    db: Session,
    user_factory: Callable[..., User],
) -> None:
    owner = user_factory(username=f"m8-owner-{uuid.uuid4().hex}")
    recipient = user_factory(username=f"m8-recipient-{uuid.uuid4().hex}")
    other = user_factory(username=f"m8-other-{uuid.uuid4().hex}")
    case, evidence = create_original(db, owner)
    original_evidence_count = db.scalar(select(func.count()).select_from(EvidenceItem).where(EvidenceItem.case_id == case.id))

    login(client, owner)
    assert client.post(
        f"/cases/{case.id}/access-grants",
        json={"recipient_username": recipient.username, "duration_hours": 25},
    ).status_code == 422
    assert client.post(
        f"/cases/{case.id}/access-grants",
        json={"recipient_username": "missing-investigator", "duration_hours": 24},
    ).status_code == 422
    created = create_grant(client, case, recipient)
    grant_id = created["id"]
    code = created["access_code"]
    persisted = db.get(CaseAccessGrant, uuid.UUID(grant_id))
    assert persisted is not None
    assert persisted.code_hash != code
    assert code not in persisted.code_hash

    login(client, recipient)
    assert client.get(f"/cases/{case.id}").status_code == 404
    assert client.post(
        f"/access-grants/{grant_id}/activate", json={"code": "x" * 32}
    ).status_code == 403

    login(client, other)
    assert client.post(
        f"/access-grants/{grant_id}/activate", json={"code": code}
    ).status_code == 404

    login(client, recipient)
    assert client.post(
        f"/access-grants/{grant_id}/activate", json={"code": code}
    ).status_code == 200
    assert client.get(f"/cases/{case.id}").status_code == 200
    assert client.get(f"/cases/{case.id}/evidence").json()["total"] == 1
    assert client.get(f"/cases/{case.id}/analysis").status_code == 200
    assert client.post(f"/cases/{case.id}/ask", json={"query": "wallet marker"}).status_code == 200
    assert client.patch(f"/cases/{case.id}", json={"name": "Forbidden"}).status_code == 404
    assert client.post(f"/cases/{case.id}/findings", json={"title": "Forbidden"}).status_code == 404
    assert client.post(f"/cases/{case.id}/sources", json={"label": "Forbidden"}).status_code == 404

    copy_response = client.post(f"/access-grants/{grant_id}/copy")
    assert copy_response.status_code == 201
    copy = copy_response.json()["case"]
    copy_id = copy["id"]
    assert copy["case_kind"] == "investigation_copy"
    assert copy["parent_case_id"] == str(case.id)
    assert copy["owner_id"] == str(recipient.id)

    login(client, owner)
    assert client.post(f"/cases/{case.id}/access-grants/{grant_id}/revoke").status_code == 200

    login(client, recipient)
    assert client.get(f"/cases/{case.id}").status_code == 404
    assert client.get(f"/cases/{copy_id}").status_code == 200
    copy_evidence = client.get(f"/cases/{copy_id}/evidence")
    assert copy_evidence.status_code == 200
    assert copy_evidence.json()["items"][0]["id"] == str(evidence.id)
    assert client.get(f"/cases/{copy_id}/analysis").status_code == 200
    assert client.post(f"/cases/{copy_id}/ask", json={"query": "wallet marker"}).status_code == 200
    copy_finding = client.post(
        f"/cases/{copy_id}/findings",
        json={"title": "Independent copy finding", "evidence_references": [evidence.evidence_reference]},
    )
    assert copy_finding.status_code == 201
    assert client.get(f"/cases/{copy_id}/report").status_code == 200

    proposal = client.post(
        f"/cases/{copy_id}/proposals",
        json={
            "title": "Proposed original finding",
            "description": "Grounded in immutable evidence.",
            "evidence_references": [evidence.evidence_reference],
        },
    )
    assert proposal.status_code == 201
    proposal_id = proposal.json()["id"]
    assert client.patch(
        f"/cases/{copy_id}/proposals/{proposal_id}", json={"title": "Updated proposal"}
    ).status_code == 200
    assert client.post(f"/cases/{copy_id}/proposals/{proposal_id}/submit").status_code == 200
    assert client.patch(
        f"/cases/{copy_id}/proposals/{proposal_id}", json={"title": "Too late"}
    ).status_code == 409

    login(client, other)
    assert client.post(f"/cases/{case.id}/proposals/{proposal_id}/accept").status_code == 404

    login(client, owner)
    accepted = client.post(f"/cases/{case.id}/proposals/{proposal_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    accepted_finding_id = accepted.json()["accepted_finding_id"]
    accepted_finding = db.get(Finding, uuid.UUID(accepted_finding_id))
    assert accepted_finding is not None
    assert accepted_finding.case_id == case.id
    assert accepted_finding.origin_proposal_id == uuid.UUID(proposal_id)
    assert db.scalar(select(func.count()).select_from(EvidenceItem).where(EvidenceItem.case_id == case.id)) == original_evidence_count
    original_titles = {item["title"] for item in client.get(f"/cases/{case.id}/findings").json()}
    assert "Independent copy finding" not in original_titles
    assert "Updated proposal" in original_titles
    audit_rows = list(db.scalars(select(AuditEvent).where(AuditEvent.case_id == case.id)))
    assert audit_rows
    assert all(code not in str(event.event_metadata) for event in audit_rows)


def test_revoked_and_expired_grants_deny_access(
    client: TestClient, db: Session, user_factory: Callable[..., User]
) -> None:
    owner = user_factory(username=f"revoke-owner-{uuid.uuid4().hex}")
    recipient = user_factory(username=f"revoke-recipient-{uuid.uuid4().hex}")
    case, _ = create_original(db, owner)
    login(client, owner)
    created = create_grant(client, case, recipient)
    login(client, recipient)
    client.post(f"/access-grants/{created['id']}/activate", json={"code": created["access_code"]})
    grant = db.get(CaseAccessGrant, uuid.UUID(created["id"]))
    assert grant is not None
    grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.get(f"/cases/{case.id}").status_code == 404


def test_reauthentication_is_session_bound_and_required_for_print(
    client: TestClient, db: Session, user_factory: Callable[..., User]
) -> None:
    owner = user_factory(username=f"reauth-owner-{uuid.uuid4().hex}")
    case, _ = create_original(db, owner)
    login(client, owner)
    assert client.post(f"/cases/{case.id}/report/print-authorize").status_code == 403
    assert client.post("/auth/reauthenticate", json={"password": "wrong-password"}).status_code == 401
    success = client.post("/auth/reauthenticate", json={"password": TEST_PASSWORD})
    assert success.status_code == 200
    until = datetime.fromisoformat(success.json()["reauthenticated_until"])
    assert until <= datetime.now(UTC) + timedelta(seconds=120)
    assert client.post(f"/cases/{case.id}/report/print-authorize").status_code == 200

    session = db.scalar(select(AuthSession).where(
        AuthSession.user_id == owner.id,
        AuthSession.reauthenticated_until.is_not(None),
    ).order_by(AuthSession.created_at.desc()))
    assert session is not None
    session.reauthenticated_until = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.post(f"/cases/{case.id}/report/print-authorize").status_code == 403

    login(client, owner)
    assert client.post(f"/cases/{case.id}/report/print-authorize").status_code == 403
