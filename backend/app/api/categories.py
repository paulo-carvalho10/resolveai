from fastapi import APIRouter, Response, status

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models import Category, Subcategory
from app.schemas.category import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    SubcategoryCreate,
    SubcategoryRead,
    SubcategoryUpdate,
)
from app.services import category_service

router = APIRouter(tags=["categories"])


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    actor: CurrentUser, db: DbSession, include_inactive: bool = False
) -> list[CategoryRead]:
    """Agents and admins may pass `include_inactive=true`; requesters only see active entries."""
    show_inactive = include_inactive and actor.is_staff
    categories = category_service.list_categories(db, actor.organization_id, show_inactive)
    result = [CategoryRead.model_validate(category) for category in categories]
    if not show_inactive:
        for category in result:
            category.subcategories = [sub for sub in category.subcategories if sub.is_active]
    return result


@router.post("/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, actor: AdminUser, db: DbSession) -> Category:
    return category_service.create_category(db, actor.organization_id, data)


@router.get("/categories/{category_id}", response_model=CategoryRead)
def get_category(category_id: int, actor: CurrentUser, db: DbSession) -> Category:
    return category_service.get_category(db, actor.organization_id, category_id)


@router.patch("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int, data: CategoryUpdate, actor: AdminUser, db: DbSession
) -> Category:
    return category_service.update_category(db, actor.organization_id, category_id, data)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, actor: AdminUser, db: DbSession) -> Response:
    category_service.delete_category(db, actor.organization_id, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/categories/{category_id}/subcategories",
    response_model=SubcategoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_subcategory(
    category_id: int, data: SubcategoryCreate, actor: AdminUser, db: DbSession
) -> Subcategory:
    return category_service.create_subcategory(db, actor.organization_id, category_id, data)


@router.patch("/subcategories/{subcategory_id}", response_model=SubcategoryRead)
def update_subcategory(
    subcategory_id: int, data: SubcategoryUpdate, actor: AdminUser, db: DbSession
) -> Subcategory:
    return category_service.update_subcategory(db, actor.organization_id, subcategory_id, data)


@router.delete("/subcategories/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subcategory(subcategory_id: int, actor: AdminUser, db: DbSession) -> Response:
    category_service.delete_subcategory(db, actor.organization_id, subcategory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
