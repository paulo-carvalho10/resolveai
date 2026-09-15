from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, DbSession, StaffUser
from app.models import User
from app.schemas.common import Page
from app.schemas.user import UserCreate, UserFilters, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserRead])
def list_users(
    actor: StaffUser, db: DbSession, filters: Annotated[UserFilters, Query()]
) -> dict[str, Any]:
    items, total = user_service.list_users(db, actor.organization_id, filters)
    return {"items": items, "total": total, "page": filters.page, "page_size": filters.page_size}


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, actor: AdminUser, db: DbSession) -> User:
    return user_service.create_user(db, actor.organization_id, data)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, actor: StaffUser, db: DbSession) -> User:
    return user_service.get_user(db, actor.organization_id, user_id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: int, data: UserUpdate, actor: AdminUser, db: DbSession) -> User:
    return user_service.update_user(db, actor, user_id, data)
