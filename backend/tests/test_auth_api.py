from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession
from app.models.user import User
from app.config import settings
from app.security import MAX_LOGIN_FAILURES, SESSION_COOKIE_NAME
from tests.conftest import TEST_PASSWORD


def test_login_me_and_logout(
    client: TestClient, db: Session, user_factory: Callable[..., User]
) -> None:
    user = user_factory(display_name="Asha Investigator")

    login = client.post(
        "/auth/login", json={"username": user.username, "password": TEST_PASSWORD}
    )

    assert login.status_code == 200
    assert login.json() == {
        "id": str(user.id),
        "username": user.username,
        "display_name": "Asha Investigator",
    }
    assert "password_hash" not in login.text
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "SameSite=lax" in login.headers["set-cookie"]
    assert db.scalar(select(AuthSession)) is not None

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)

    logout = client.post("/auth/logout")
    assert logout.status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert db.scalar(select(AuthSession)) is None


def test_login_failure_uses_generic_error(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user_factory()
    response = client.post(
        "/auth/login", json={"username": "investigator", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"
    assert SESSION_COOKIE_NAME not in client.cookies


def test_inactive_user_cannot_login(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user_factory(is_active=False)
    response = client.post(
        "/auth/login",
        json={"username": "investigator", "password": TEST_PASSWORD},
    )
    assert response.status_code == 403


def test_login_rate_limit(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user_factory()
    for _ in range(MAX_LOGIN_FAILURES):
        response = client.post(
            "/auth/login", json={"username": "investigator", "password": "wrong"}
        )
        assert response.status_code == 401

    response = client.post(
        "/auth/login",
        json={"username": "investigator", "password": TEST_PASSWORD},
    )
    assert response.status_code == 429


def test_protected_endpoint_requires_authentication(client: TestClient) -> None:
    assert client.get("/cases").status_code == 401


def test_cors_allows_only_configured_frontend(client: TestClient) -> None:
    allowed = client.options(
        "/auth/login",
        headers={
            "Origin": settings.frontend_origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == settings.frontend_origin
    assert allowed.headers["access-control-allow-credentials"] == "true"

    denied = client.options(
        "/auth/login",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in denied.headers
