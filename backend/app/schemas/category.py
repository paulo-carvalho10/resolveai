from pydantic import BaseModel, Field

from app.schemas.common import Name, ORMModel


class SubcategoryRead(ORMModel):
    id: int
    category_id: int
    name: str
    description: str | None
    is_active: bool


class CategoryRead(ORMModel):
    id: int
    name: str
    description: str | None
    default_team_id: int | None
    is_active: bool
    subcategories: list[SubcategoryRead]


class SubcategoryCreate(BaseModel):
    name: Name
    description: str | None = Field(None, max_length=2000)


class SubcategoryUpdate(BaseModel):
    name: Name | None = None
    description: str | None = Field(None, max_length=2000)
    is_active: bool | None = None


class CategoryCreate(BaseModel):
    name: Name
    description: str | None = Field(None, max_length=2000)
    default_team_id: int | None = None
    subcategories: list[SubcategoryCreate] = []


class CategoryUpdate(BaseModel):
    name: Name | None = None
    description: str | None = Field(None, max_length=2000)
    default_team_id: int | None = None
    is_active: bool | None = None
