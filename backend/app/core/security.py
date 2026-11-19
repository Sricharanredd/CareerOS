"""Password hashing, token minting and cookie constants."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)

ACCESS_COOKIE = "careeros_access"
REFRESH_COOKIE = "careeros_refresh"
CSRF_COOKIE = "careeros_csrf"
CSRF_HEADER = "X-CSRF-Token"
REFRESH_COOKIE_PATH = "/api/v1/auth"

JWT_ALGORITHM = "HS256"


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# ------------------------------------------------------------------- tokens
def utcnow() -> datetime:
    """Naive UTC timestamp, matching the DATETIME(6) columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def create_access_token(*, owner_id: str, session_id: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = utcnow() + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": owner_id,
        "sid": session_id,
        "typ": "access",
        "jti": secrets.token_urlsafe(16),
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int(expires_at.replace(tzinfo=UTC).timestamp()),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub", "sid"]},
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def generate_refresh_token() -> tuple[str, str]:
    """Return (raw token handed to the client, sha256 hash stored in MySQL)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_equals(left: str, right: str) -> bool:
    return secrets.compare_digest(left, right)
