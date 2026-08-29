from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_auth_session, get_current_user
from app.audit import audit_event
from app.config import settings
from app.db.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas import LoginRequest, ReauthenticateRequest, ReauthenticateResponse, UserResponse
from app.security import (
    SESSION_COOKIE_NAME,
    clear_login_failures,
    hash_session_token,
    login_is_limited,
    new_session_token,
    record_login_failure,
    session_expiry,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
REAUTH_WINDOW_SECONDS = 120


def _login_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.strip().lower()}"


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    username = payload.username.strip().lower()
    key = _login_key(request, username)
    if login_is_limited(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)

    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(payload.password, user.password_hash):
        record_login_failure(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if not user.is_active:
        record_login_failure(key)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

    clear_login_failures(key)
    token = new_session_token()
    expires_at = session_expiry()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
        )
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        expires=expires_at,
        path="/",
    )
    return user


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/reauthenticate", response_model=ReauthenticateResponse)
def reauthenticate(
    payload: ReauthenticateRequest,
    auth_session: AuthSession = Depends(get_current_auth_session),
    db: Session = Depends(get_db),
) -> ReauthenticateResponse:
    user = db.get(User, auth_session.user_id)
    if user is None or not verify_password(payload.password, user.password_hash):
        audit_event(db, action="password_reauthenticate", success=False, user_id=auth_session.user_id)
        db.commit()
        raise HTTPException(status_code=401, detail="Reauthentication failed")
    from datetime import UTC, datetime, timedelta

    auth_session.reauthenticated_until = datetime.now(UTC) + timedelta(seconds=REAUTH_WINDOW_SECONDS)
    audit_event(db, action="password_reauthenticate", success=True, user_id=user.id)
    db.commit()
    return ReauthenticateResponse(reauthenticated_until=auth_session.reauthenticated_until)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> None:
    if session_token:
        db.execute(
            delete(AuthSession).where(
                AuthSession.token_hash == hash_session_token(session_token)
            )
        )
        db.commit()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )
