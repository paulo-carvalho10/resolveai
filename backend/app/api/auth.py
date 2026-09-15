from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.models import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.user import UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: DbSession) -> TokenPair:
    """Create a new organization and its first administrator."""
    return auth_service.issue_tokens(auth_service.register(db, data))


@router.post("/login", response_model=TokenPair)
def login(data: LoginRequest, db: DbSession) -> TokenPair:
    return auth_service.issue_tokens(auth_service.authenticate(db, data.email, data.password))


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshRequest, db: DbSession) -> TokenPair:
    return auth_service.issue_tokens(auth_service.refresh(db, data.refresh_token))


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
