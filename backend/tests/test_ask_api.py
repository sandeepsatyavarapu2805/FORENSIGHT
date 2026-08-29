import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.provider import (
    DisabledAIProvider,
    EvidenceContextItem,
    OpenAICompatibleProvider,
    ProviderAnswer,
    ProviderError,
    get_ai_provider,
)
from app.config import settings
from app.main import app
from app.models.case import Case
from app.models.evidence_item import EvidenceItem
from app.models.evidence_source import EvidenceSource
from app.models.user import User
from tests.conftest import TEST_PASSWORD


class StaticProvider:
    def __init__(self, result: ProviderAnswer) -> None:
        self.result = result
        self.context: tuple[EvidenceContextItem, ...] = ()

    def answer(
        self,
        question: str,
        evidence: tuple[EvidenceContextItem, ...],
    ) -> ProviderAnswer:
        self.context = evidence
        return self.result


class FailingProvider:
    def answer(
        self,
        question: str,
        evidence: tuple[EvidenceContextItem, ...],
    ) -> ProviderAnswer:
        raise ProviderError("provider timeout")


def use_provider(provider: object) -> None:
    app.dependency_overrides[get_ai_provider] = lambda: provider


def create_ask_case(
    db: Session,
    owner: User,
) -> tuple[Case, EvidenceItem]:
    case = Case(
        case_identifier=f"FS-ASK-{uuid.uuid4().hex[:8]}",
        name="Ask Case",
        owner_id=owner.id,
    )

    db.add(case)
    db.flush()

    source = EvidenceSource(
        case_id=case.id,
        label="Ask Device",
    )

    db.add(source)
    db.flush()

    item = EvidenceItem(
        evidence_reference=(
            f"MSG-{uuid.uuid4().hex[:12].upper()}"
        ),
        case_id=case.id,
        source_id=source.id,
        artifact_type="message",
        original_record_id="message-crypto-1",
        searchable_text=(
            "Alice discussed cryptocurrency payment "
            "using wallet address 0xABC123."
        ),
        data={},
        raw_metadata={},
        application="ChatApp",
        parser_identifier="test.fixture",
        parser_version="1",
    )

    db.add(item)
    db.commit()

    return case, item


def test_ask_returns_grounded_evidence_citations(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client

    case, item = create_ask_case(
        db,
        user,
    )

    response = client.post(
        f"/cases/{case.id}/ask",
        json={
            "query": "cryptocurrency wallet",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["sufficient_evidence"] is True
    assert len(body["citations"]) >= 1

    citation = body["citations"][0]

    assert citation["evidence_id"] == str(item.id)
    assert (
        citation["evidence_reference"]
        == item.evidence_reference
    )

    assert "cryptocurrency" in (
        citation["excerpt"].lower()
    )


def test_ask_returns_explicit_insufficient_evidence(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client

    case, _ = create_ask_case(
        db,
        user,
    )

    response = client.post(
        f"/cases/{case.id}/ask",
        json={
            "query": "completely unrelated zebra",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["sufficient_evidence"] is False
    assert body["citations"] == []
    assert "Insufficient evidence" in body["answer"]


def test_ask_exact_evidence_reference_is_retrievable(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client

    case, item = create_ask_case(
        db,
        user,
    )

    response = client.post(
        f"/cases/{case.id}/ask",
        json={
            "query": item.evidence_reference,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["sufficient_evidence"] is True
    assert (
        body["citations"][0]["evidence_reference"]
        == item.evidence_reference
    )


def test_ask_rejects_blank_query(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client

    case, _ = create_ask_case(
        db,
        user,
    )

    response = client.post(
        f"/cases/{case.id}/ask",
        json={"query": "   "},
    )

    assert response.status_code == 422


def test_ask_preserves_case_isolation(
    client: TestClient,
    db: Session,
    user_factory: Callable[..., User],
) -> None:
    owner = user_factory(
        username="ask-owner",
    )

    intruder = user_factory(
        username="ask-intruder",
    )

    case, _ = create_ask_case(
        db,
        owner,
    )

    client.post(
        "/auth/login",
        json={
            "username": intruder.username,
            "password": TEST_PASSWORD,
        },
    )

    response = client.post(
        f"/cases/{case.id}/ask",
        json={
            "query": "cryptocurrency",
        },
    )

    assert response.status_code == 404


def test_ask_uses_grounded_provider_and_validates_citations(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client
    case, item = create_ask_case(db, user)
    provider = StaticProvider(
        ProviderAnswer(
            answer="The supplied message contains a cryptocurrency wallet reference.",
            citations=(item.evidence_reference, "MSG-FABRICATED"),
            insufficient_evidence=False,
        )
    )
    use_provider(provider)

    response = client.post(
        f"/cases/{case.id}/ask", json={"query": "cryptocurrency wallet"}
    )

    assert response.status_code == 200
    assert response.json()["answer"].startswith("The supplied message")
    assert [citation["evidence_reference"] for citation in response.json()["citations"]] == [
        item.evidence_reference
    ]
    assert len(provider.context) == 1
    assert provider.context[0].evidence_reference == item.evidence_reference
    assert "cryptocurrency" in provider.context[0].searchable_excerpt.lower()


def test_ask_rejects_fabricated_only_citations_and_uses_fallback(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client
    case, item = create_ask_case(db, user)
    use_provider(
        StaticProvider(
            ProviderAnswer(
                answer="Unsupported model claim",
                citations=("MSG-FABRICATED",),
                insufficient_evidence=False,
            )
        )
    )

    response = client.post(
        f"/cases/{case.id}/ask", json={"query": "cryptocurrency"}
    )

    assert response.status_code == 200
    assert response.json()["answer"].startswith("ForenSight found")
    assert response.json()["citations"][0]["evidence_reference"] == item.evidence_reference
    assert "MSG-FABRICATED" not in response.text


def test_ask_provider_failure_uses_deterministic_fallback(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client
    case, item = create_ask_case(db, user)
    use_provider(FailingProvider())

    response = client.post(
        f"/cases/{case.id}/ask", json={"query": "cryptocurrency"}
    )

    assert response.status_code == 200
    assert response.json()["sufficient_evidence"] is True
    assert response.json()["citations"][0]["evidence_reference"] == item.evidence_reference


def test_ask_provider_can_return_explicit_insufficient_evidence(
    authenticated_client: tuple[TestClient, User],
    db: Session,
) -> None:
    client, user = authenticated_client
    case, _ = create_ask_case(db, user)
    use_provider(
        StaticProvider(
            ProviderAnswer(
                answer="The supplied evidence is insufficient for that conclusion.",
                citations=(),
                insufficient_evidence=True,
            )
        )
    )

    response = client.post(
        f"/cases/{case.id}/ask", json={"query": "cryptocurrency conclusion"}
    )

    assert response.status_code == 200
    assert response.json()["sufficient_evidence"] is False
    assert response.json()["citations"] == []


def test_openai_compatible_provider_rejects_bad_json(
    monkeypatch,
) -> None:
    class InvalidResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "not-json"}}]}

    monkeypatch.setattr("app.ai.provider.httpx.post", lambda *args, **kwargs: InvalidResponse())
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://provider.invalid/v1",
        timeout_seconds=1,
    )

    try:
        provider.answer(
            "question",
            (
                EvidenceContextItem(
                    evidence_reference="MSG-1",
                    artifact_type="message",
                    application=None,
                    occurred_at=None,
                    searchable_excerpt="bounded evidence",
                    normalized_data_excerpt="{}",
                ),
            ),
        )
    except ProviderError:
        pass
    else:
        raise AssertionError("Invalid provider JSON must raise ProviderError")


def test_missing_provider_configuration_uses_disabled_provider(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "ai_api_key", None)
    monkeypatch.setattr(settings, "ai_model", None)
    assert isinstance(get_ai_provider(), DisabledAIProvider)
