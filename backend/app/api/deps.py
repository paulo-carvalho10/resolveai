from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.models import User, UserRole
from app.services import auth_service
from app.services.ai_classifier import Classifier, build_classifier
from app.services.answer_generator import AnswerGenerator, build_answer_generator
from app.services.embeddings import Embedder, build_embedder

DbSession = Annotated[Session, Depends(get_db)]


# One instance per process: the HTTP clients inside pool connections.
@lru_cache
def get_classifier() -> Classifier:
    return build_classifier(get_settings())


@lru_cache
def get_embedder() -> Embedder:
    return build_embedder(get_settings())


@lru_cache
def get_answer_generator() -> AnswerGenerator:
    return build_answer_generator(get_settings())


def get_session_factory() -> Callable[[], Session]:
    """Background tasks outlive the request session, so they open their own."""
    return SessionLocal


ClassifierDep = Annotated[Classifier, Depends(get_classifier)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
AnswerGeneratorDep = Annotated[AnswerGenerator, Depends(get_answer_generator)]
SessionFactory = Annotated[Callable[[], Session], Depends(get_session_factory)]

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise AuthenticationError("NOT_AUTHENTICATED", "Authentication required.")
    return auth_service.get_user_from_access_token(db, credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDeniedError()
        return user

    return dependency


StaffUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.AGENT))]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
