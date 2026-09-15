from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Name, ORMModel
from app.schemas.user import UserSummary


class TeamRead(ORMModel):
    id: int
    name: str
    description: str | None
    members: list[UserSummary]
    created_at: datetime


class TeamCreate(BaseModel):
    name: Name
    description: str | None = Field(None, max_length=2000)


class TeamUpdate(BaseModel):
    name: Name | None = None
    description: str | None = Field(None, max_length=2000)


class TeamMemberAdd(BaseModel):
    user_id: int
