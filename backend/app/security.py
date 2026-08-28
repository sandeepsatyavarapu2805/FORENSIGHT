import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash

from app.config import settings

SESSION_COOKIE_NAME = "forensight_session"
MAX_LOGIN_FAILURES = 5
LOGIN_WINDOW_SECONDS = 300

password_hasher = PasswordHash.recommended()
_login_failures: dict[str, deque[float]] = defaultdict(deque)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(hours=settings.session_lifetime_hours)


def _recent_failures(key: str) -> deque[float]:
    failures = _login_failures[key]
    cutoff = time.monotonic() - LOGIN_WINDOW_SECONDS
    while failures and failures[0] < cutoff:
        failures.popleft()
    return failures


def login_is_limited(key: str) -> bool:
    return len(_recent_failures(key)) >= MAX_LOGIN_FAILURES


def record_login_failure(key: str) -> None:
    _recent_failures(key).append(time.monotonic())


def clear_login_failures(key: str) -> None:
    _login_failures.pop(key, None)


def reset_login_limiter() -> None:
    _login_failures.clear()
