from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field

from app.models.enums import TicketEventType, TicketPriority, TicketStatus
from app.schemas.common import NamedRef, ORMModel, PageParams
from app.schemas.user import UserSummary
from app.services import sla

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=200)]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=10, max_length=20000)
]
MessageBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)
]

TicketSort = Literal[
    "created_at", "-created_at", "updated_at", "-updated_at", "priority", "-priority"
]


class TicketCreate(BaseModel):
    title: Title
    description: Description
    category_id: int | None = None
    subcategory_id: int | None = None


class TicketUpdate(BaseModel):
    """Partial update. Sending `null` for category, subcategory or team clears it."""

    title: Title | None = None
    description: Description | None = None
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    team_id: int | None = None


class TicketAssign(BaseModel):
    """Omit `assignee_id` to assign the ticket to yourself."""

    assignee_id: int | None = None


class TicketResolve(BaseModel):
    resolution: MessageBody | None = None


class TicketRead(ORMModel):
    id: int
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    category: NamedRef | None
    subcategory: NamedRef | None
    team: NamedRef | None
    requester: UserSummary
    assignee: UserSummary | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    # Latest AI suggestion. Shown next to the real fields even when it was not applied.
    ai_category: NamedRef | None
    ai_subcategory: NamedRef | None
    ai_team: NamedRef | None
    ai_priority: TicketPriority | None
    ai_confidence: float | None
    ai_summary: str | None
    ai_analyzed_at: datetime | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sla_due_at(self) -> datetime:
        return sla.due_at(self.priority, self.created_at)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sla_status(self) -> sla.SlaStatus:
        return sla.status(self.priority, self.status, self.created_at, self.resolved_at)


class TicketFilters(PageParams):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(None, description="Search in title and description, or by id (#123).")
    status: list[TicketStatus] = Field(default_factory=list)
    priority: list[TicketPriority] = Field(default_factory=list)
    category_id: int | None = None
    subcategory_id: int | None = None
    team_id: int | None = None
    assignee_id: int | None = None
    requester_id: int | None = None
    unassigned: bool = False
    created_from: date | None = None
    created_to: date | None = None
    sort: TicketSort = "-created_at"


class MessageCreate(BaseModel):
    body: MessageBody
    is_internal: bool = False


class MessageRead(ORMModel):
    id: int
    ticket_id: int
    author: UserSummary
    body: str
    is_internal: bool
    created_at: datetime


class HistoryRead(ORMModel):
    id: int
    event_type: TicketEventType
    field: str | None
    old_value: str | None
    new_value: str | None
    actor: UserSummary | None
    created_at: datetime
