from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.session import engine, get_db
from app.main import app
from app.models.auth_session import AuthSession
from app.models.case import Case
from app.models.evidence_source import EvidenceSource
from app.models.user import User
from app.security import hash_password, reset_login_limiter

TEST_PASSWORD = "Correct horse battery staple!"


@pytest.fixture
def db() -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    reset_login_limiter()

    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    reset_login_limiter()


@pytest.fixture
def user_factory(db: Session) -> Callable[..., User]:
    def create_user(
        username: str = "investigator",
        password: str = TEST_PASSWORD,
        display_name: str = "Test Investigator",
        is_active: bool = True,
    ) -> User:
        user = User(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return create_user


@pytest.fixture
def authenticated_client(
    client: TestClient, user_factory: Callable[..., User]
) -> tuple[TestClient, User]:
    user = user_factory()
    response = client.post(
        "/auth/login",
        json={"username": user.username, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return client, user
