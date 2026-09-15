import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, AuthenticationError
from app.core.logger import log_event
from app.core.security import (
    TokenType,
    burn_password_check,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import Organization, User, UserRole
from app.schemas.auth import RegisterRequest, TokenPair
from app.services import user_service

logger = logging.getLogger(__name__)


def register(db: Session, data: RegisterRequest) -> User:
    user_service.ensure_email_available(db, data.email)
    organization = Organization(name=data.organization_name)
    admin = User(
        organization=organization,
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=UserRole.ADMIN,
    )
    db.add(admin)
    db.commit()
    log_event(logger, "organization.registered", organization_id=organization.id, user_id=admin.id)
    return admin


def authenticate(db: Session, email: str, password: str) -> User:
    user = user_service.find_by_email(db, email)
    if user is None:
        burn_password_check(password)
        raise AuthenticationError("INVALID_CREDENTIALS", "Invalid email or password.")
    if not verify_password(password, user.hashed_password):
        log_event(logger, "auth.login_failed", level=logging.WARNING, user_id=user.id)
        raise AuthenticationError("INVALID_CREDENTIALS", "Invalid email or password.")
    if not user.is_active:
        raise AppError("USER_INACTIVE", "This account has been deactivated.", 403)
    log_event(logger, "auth.login", user_id=user.id)
    return user


def refresh(db: Session, refresh_token: str) -> User:
    user = db.get(User, decode_token(refresh_token, TokenType.REFRESH))
    if user is None or not user.is_active:
        raise AuthenticationError("INVALID_TOKEN", "Invalid token.")
    return user


def get_user_from_access_token(db: Session, access_token: str) -> User:
    user = db.get(User, decode_token(access_token, TokenType.ACCESS))
    if user is None or not user.is_active:
        raise AuthenticationError("INVALID_TOKEN", "Invalid token.")
    return user


def issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, TokenType.ACCESS),
        refresh_token=create_token(user.id, TokenType.REFRESH),
        expires_in=get_settings().access_token_expire_minutes * 60,
    )
