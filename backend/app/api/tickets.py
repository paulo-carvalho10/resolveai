from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Query, Response, status

from app.api.deps import (
    AdminUser,
    ClassifierDep,
    CurrentUser,
    DbSession,
    SessionFactory,
    StaffUser,
)
from app.core.config import get_settings
from app.models import Ticket, TicketAIAnalysis, TicketHistory, TicketMessage
from app.schemas.ai import AnalysisRead
from app.schemas.common import Page
from app.schemas.ticket import (
    HistoryRead,
    MessageCreate,
    MessageRead,
    TicketAssign,
    TicketCreate,
    TicketFilters,
    TicketRead,
    TicketResolve,
    TicketUpdate,
)
from app.services import ticket_service, triage_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=Page[TicketRead])
def list_tickets(
    actor: CurrentUser, db: DbSession, filters: Annotated[TicketFilters, Query()]
) -> dict[str, Any]:
    """Agents and admins see the whole organization; requesters only see their own tickets."""
    items, total = ticket_service.list_tickets(db, actor, filters)
    return {"items": items, "total": total, "page": filters.page, "page_size": filters.page_size}


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
def create_ticket(
    data: TicketCreate,
    actor: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    classifier: ClassifierDep,
    session_factory: SessionFactory,
) -> Ticket:
    """Priority rules and routing run immediately; AI classification runs after the response."""
    ticket = ticket_service.create_ticket(db, actor, data)
    if get_settings().ai_analyze_on_create:
        background_tasks.add_task(
            triage_service.analyze_in_background, session_factory, classifier, ticket.id
        )
    return ticket


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket(ticket_id: int, actor: CurrentUser, db: DbSession) -> Ticket:
    return ticket_service.get_ticket(db, actor, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketRead)
def update_ticket(ticket_id: int, data: TicketUpdate, actor: StaffUser, db: DbSession) -> Ticket:
    return ticket_service.update_ticket(db, actor, ticket_id, data)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(ticket_id: int, actor: AdminUser, db: DbSession) -> Response:
    ticket_service.delete_ticket(db, actor, ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{ticket_id}/assign", response_model=TicketRead)
def assign_ticket(ticket_id: int, data: TicketAssign, actor: StaffUser, db: DbSession) -> Ticket:
    return ticket_service.assign_ticket(db, actor, ticket_id, data.assignee_id)


@router.post("/{ticket_id}/resolve", response_model=TicketRead)
def resolve_ticket(ticket_id: int, data: TicketResolve, actor: StaffUser, db: DbSession) -> Ticket:
    return ticket_service.resolve_ticket(db, actor, ticket_id, data)


@router.get("/{ticket_id}/messages", response_model=list[MessageRead])
def list_messages(ticket_id: int, actor: CurrentUser, db: DbSession) -> list[TicketMessage]:
    """Internal notes are hidden from requesters."""
    return ticket_service.list_messages(db, actor, ticket_id)


@router.post(
    "/{ticket_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED
)
def add_message(
    ticket_id: int, data: MessageCreate, actor: CurrentUser, db: DbSession
) -> TicketMessage:
    return ticket_service.add_message(db, actor, ticket_id, data)


@router.get("/{ticket_id}/history", response_model=list[HistoryRead])
def list_history(ticket_id: int, actor: StaffUser, db: DbSession) -> list[TicketHistory]:
    return ticket_service.list_history(db, actor, ticket_id)


@router.post("/{ticket_id}/ai/analyze", response_model=AnalysisRead)
def analyze_ticket(
    ticket_id: int, actor: StaffUser, db: DbSession, classifier: ClassifierDep
) -> TicketAIAnalysis:
    """Run the AI classification now and apply the result under the same safety rules."""
    ticket = ticket_service.get_ticket(db, actor, ticket_id)
    return triage_service.analyze_ticket_on_request(db, ticket, classifier, actor)


@router.get("/{ticket_id}/ai/analyses", response_model=list[AnalysisRead])
def list_analyses(ticket_id: int, actor: StaffUser, db: DbSession) -> list[TicketAIAnalysis]:
    """Every classification run for this ticket, newest first."""
    ticket = ticket_service.get_ticket(db, actor, ticket_id)
    return triage_service.list_analyses(db, ticket)
