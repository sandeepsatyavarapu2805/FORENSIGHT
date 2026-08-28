from datetime import UTC, datetime

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.security import SESSION_COOKIE_NAME, hash_session_token


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hash_session_token(session_token),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    if auth_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user
