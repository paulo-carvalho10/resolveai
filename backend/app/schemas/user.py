from datetime import datetime

from pydantic import BaseModel

from app.models.enums import UserRole
from app.schemas.auth import FullName
from app.schemas.common import NormalizedEmail, ORMModel, PageParams, Password


class UserSummary(ORMModel):
    id: int
    full_name: str
    email: str


class UserRead(ORMModel):
    id: int
    organization_id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: NormalizedEmail
    full_name: FullName
    password: Password
    role: UserRole = UserRole.USER


class UserUpdate(BaseModel):
    full_name: FullName | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserFilters(PageParams):
    q: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
