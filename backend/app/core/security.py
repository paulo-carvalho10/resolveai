from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import cache
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.core.errors import AuthenticationError

_hasher = PasswordHasher()


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, password)
    except (VerificationError, InvalidHashError):
        return False


@cache
def _dummy_hash() -> str:
    return _hasher.hash("resolveai-timing-equalizer")


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check so login does not reveal which emails exist."""
    verify_password(password, _dummy_hash())


def create_token(user_id: int, token_type: TokenType) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    if token_type is TokenType.ACCESS:
        lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    else:
        lifetime = timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "type": token_type.value,
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> int:
    """Validate a JWT and return the user id it was issued for."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("TOKEN_EXPIRED", "Token has expired.") from None
    except jwt.InvalidTokenError:
        raise AuthenticationError("INVALID_TOKEN", "Invalid token.") from None

    subject = payload["sub"]
    if payload["type"] != expected_type.value or not str(subject).isdigit():
        raise AuthenticationError("INVALID_TOKEN", "Invalid token.")
    return int(subject)
