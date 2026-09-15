import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.logger import log_event
from app.core.security import hash_password
from app.models import User
from app.schemas.user import UserCreate, UserFilters, UserUpdate

logger = logging.getLogger(__name__)


def find_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def ensure_email_available(db: Session, email: str) -> None:
    if find_by_email(db, email) is not None:
        raise ConflictError("EMAIL_ALREADY_REGISTERED", "This email is already registered.")


def get_user(db: Session, organization_id: int, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        raise NotFoundError("User")
    return user


def list_users(db: Session, organization_id: int, filters: UserFilters) -> tuple[list[User], int]:
    stmt = select(User).where(User.organization_id == organization_id)
    if filters.role is not None:
        stmt = stmt.where(User.role == filters.role)
    if filters.is_active is not None:
        stmt = stmt.where(User.is_active == filters.is_active)
    if filters.q:
        term = filters.q.strip()
        stmt = stmt.where(
            or_(
                User.full_name.icontains(term, autoescape=True),
                User.email.icontains(term, autoescape=True),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(User.full_name, User.id).offset(filters.offset).limit(filters.page_size)
    return list(db.scalars(stmt)), total


def create_user(db: Session, organization_id: int, data: UserCreate) -> User:
    ensure_email_available(db, data.email)
    user = User(
        organization_id=organization_id,
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    log_event(logger, "user.created", user_id=user.id, organization_id=organization_id)
    return user


def update_user(db: Session, actor: User, user_id: int, data: UserUpdate) -> User:
    user = get_user(db, actor.organization_id, user_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)

    # Prevents an organization from locking itself out by accident.
    if user.id == actor.id and (
        changes.get("role", user.role) != user.role or changes.get("is_active") is False
    ):
        raise AppError(
            "CANNOT_MODIFY_SELF", "You cannot change your own role or deactivate yourself.", 422
        )

    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    log_event(logger, "user.updated", user_id=user.id, actor_id=actor.id, fields=",".join(changes))
    return user
