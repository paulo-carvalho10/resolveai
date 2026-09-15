from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.models.enums import AnalysisStatus, TicketPriority
from app.schemas.common import Name, NamedRef, ORMModel
from app.schemas.user import UserSummary

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class PriorityRuleRead(ORMModel):
    id: int
    name: str
    keywords: list[str]
    priority: TicketPriority
    is_active: bool
    created_at: datetime


class PriorityRuleCreate(BaseModel):
    name: Name
    keywords: list[Keyword] = Field(min_length=1, max_length=50)
    priority: TicketPriority
    is_active: bool = True


class PriorityRuleUpdate(BaseModel):
    name: Name | None = None
    keywords: list[Keyword] | None = Field(None, min_length=1, max_length=50)
    priority: TicketPriority | None = None
    is_active: bool | None = None


class AnalysisRead(ORMModel):
    id: int
    status: AnalysisStatus
    provider: str
    model: str
    category_name: str | None
    subcategory_name: str | None
    team_name: str | None
    priority: TicketPriority | None
    urgency: TicketPriority | None
    summary: str | None
    reasoning: str | None
    confidence: float | None
    matched_rule: NamedRef | None
    applied_fields: list[str]
    error_code: str | None
    requested_by: UserSummary | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    created_at: datetime

    @field_validator("applied_fields", mode="before")
    @classmethod
    def _split_fields(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [field for field in value.split(",") if field]
        return value
