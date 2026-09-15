import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.core.logger import log_event
from app.models import Category, Subcategory
from app.schemas.category import (
    CategoryCreate,
    CategoryUpdate,
    SubcategoryCreate,
    SubcategoryUpdate,
)
from app.services import team_service

logger = logging.getLogger(__name__)


def list_categories(db: Session, organization_id: int, include_inactive: bool) -> list[Category]:
    stmt = (
        select(Category)
        .where(Category.organization_id == organization_id)
        .options(selectinload(Category.subcategories))
        .order_by(Category.name)
    )
    if not include_inactive:
        stmt = stmt.where(Category.is_active.is_(True))
    return list(db.scalars(stmt))


def get_category(db: Session, organization_id: int, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None or category.organization_id != organization_id:
        raise NotFoundError("Category")
    return category


def get_subcategory(db: Session, organization_id: int, subcategory_id: int) -> Subcategory:
    subcategory = db.get(Subcategory, subcategory_id)
    if subcategory is None or subcategory.category.organization_id != organization_id:
        raise NotFoundError("Subcategory")
    return subcategory


def _ensure_category_name_available(
    db: Session, organization_id: int, name: str, exclude_id: int | None = None
) -> None:
    stmt = select(Category.id).where(
        Category.organization_id == organization_id, func.lower(Category.name) == name.lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise ConflictError("CATEGORY_NAME_TAKEN", "A category with this name already exists.")


def _ensure_subcategory_name_available(
    category: Category, name: str, exclude_id: int | None = None
) -> None:
    for subcategory in category.subcategories:
        if subcategory.id != exclude_id and subcategory.name.lower() == name.lower():
            raise ConflictError(
                "SUBCATEGORY_NAME_TAKEN", "This category already has a subcategory with this name."
            )


def create_category(db: Session, organization_id: int, data: CategoryCreate) -> Category:
    _ensure_category_name_available(db, organization_id, data.name)
    if data.default_team_id is not None:
        team_service.get_team(db, organization_id, data.default_team_id)

    category = Category(
        organization_id=organization_id,
        name=data.name,
        description=data.description,
        default_team_id=data.default_team_id,
    )
    for sub in data.subcategories:
        _ensure_subcategory_name_available(category, sub.name)
        category.subcategories.append(Subcategory(name=sub.name, description=sub.description))
    db.add(category)
    db.commit()
    log_event(logger, "category.created", category_id=category.id, organization_id=organization_id)
    return category


def update_category(
    db: Session, organization_id: int, category_id: int, data: CategoryUpdate
) -> Category:
    category = get_category(db, organization_id, category_id)
    changes = data.model_dump(exclude_unset=True)

    if changes.get("name") is not None:
        _ensure_category_name_available(db, organization_id, changes["name"], category.id)
        category.name = changes["name"]
    if "description" in changes:
        category.description = changes["description"]
    if "default_team_id" in changes:
        if changes["default_team_id"] is not None:
            team_service.get_team(db, organization_id, changes["default_team_id"])
        category.default_team_id = changes["default_team_id"]
    if changes.get("is_active") is not None:
        category.is_active = changes["is_active"]
    db.commit()
    return category


def delete_category(db: Session, organization_id: int, category_id: int) -> None:
    category = get_category(db, organization_id, category_id)
    db.delete(category)
    db.commit()
    log_event(logger, "category.deleted", category_id=category_id, organization_id=organization_id)


def create_subcategory(
    db: Session, organization_id: int, category_id: int, data: SubcategoryCreate
) -> Subcategory:
    category = get_category(db, organization_id, category_id)
    _ensure_subcategory_name_available(category, data.name)
    subcategory = Subcategory(name=data.name, description=data.description)
    category.subcategories.append(subcategory)
    db.commit()
    return subcategory


def update_subcategory(
    db: Session, organization_id: int, subcategory_id: int, data: SubcategoryUpdate
) -> Subcategory:
    subcategory = get_subcategory(db, organization_id, subcategory_id)
    changes = data.model_dump(exclude_unset=True)

    if changes.get("name") is not None:
        _ensure_subcategory_name_available(subcategory.category, changes["name"], subcategory.id)
        subcategory.name = changes["name"]
    if "description" in changes:
        subcategory.description = changes["description"]
    if changes.get("is_active") is not None:
        subcategory.is_active = changes["is_active"]
    db.commit()
    return subcategory


def delete_subcategory(db: Session, organization_id: int, subcategory_id: int) -> None:
    subcategory = get_subcategory(db, organization_id, subcategory_id)
    db.delete(subcategory)
    db.commit()
