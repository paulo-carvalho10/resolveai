"""Ticket lifecycle: creation, triage, assignment, conversation and audit history."""

import logging
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.core.logger import log_event
from app.models import (
    Category,
    Subcategory,
    Ticket,
    TicketEventType,
    TicketHistory,
    TicketMessage,
    TicketPriority,
    TicketStatus,
    User,
)
from app.models.base import utcnow
from app.schemas.ticket import (
    MessageCreate,
    TicketCreate,
    TicketFilters,
    TicketResolve,
    TicketUpdate,
)
from app.services import category_service, team_service, triage_service, user_service
from app.services.ticket_history import display_name, record_event

logger = logging.getLogger(__name__)

_TICKET_RELATIONS = (
    selectinload(Ticket.requester),
    selectinload(Ticket.assignee),
    selectinload(Ticket.team),
    selectinload(Ticket.category),
    selectinload(Ticket.subcategory),
    selectinload(Ticket.ai_team),
    selectinload(Ticket.ai_category),
    selectinload(Ticket.ai_subcategory),
)

_PRIORITY_RANK = case(
    {priority: rank for rank, priority in enumerate(TicketPriority)}, value=Ticket.priority
)

_SORT_COLUMNS = {
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
    "priority": _PRIORITY_RANK,
}


# --- Queries -------------------------------------------------------------------------------


def get_ticket(db: Session, actor: User, ticket_id: int) -> Ticket:
    """Load a ticket the actor may see. Requesters only see their own tickets."""
    ticket = db.scalar(
        select(Ticket)
        .where(Ticket.id == ticket_id, Ticket.organization_id == actor.organization_id)
        .options(*_TICKET_RELATIONS)
    )
    # 404 instead of 403 so users cannot probe which ticket ids exist.
    if ticket is None or (not actor.is_staff and ticket.requester_id != actor.id):
        raise NotFoundError("Ticket")
    return ticket


def list_tickets(db: Session, actor: User, filters: TicketFilters) -> tuple[list[Ticket], int]:
    stmt = select(Ticket).where(Ticket.organization_id == actor.organization_id)

    if not actor.is_staff:
        stmt = stmt.where(Ticket.requester_id == actor.id)
    elif filters.requester_id is not None:
        stmt = stmt.where(Ticket.requester_id == filters.requester_id)

    if filters.status:
        stmt = stmt.where(Ticket.status.in_(filters.status))
    if filters.priority:
        stmt = stmt.where(Ticket.priority.in_(filters.priority))
    if filters.category_id is not None:
        stmt = stmt.where(Ticket.category_id == filters.category_id)
    if filters.subcategory_id is not None:
        stmt = stmt.where(Ticket.subcategory_id == filters.subcategory_id)
    if filters.team_id is not None:
        stmt = stmt.where(Ticket.team_id == filters.team_id)
    if filters.unassigned:
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    elif filters.assignee_id is not None:
        stmt = stmt.where(Ticket.assignee_id == filters.assignee_id)
    if filters.created_from is not None:
        stmt = stmt.where(
            Ticket.created_at >= datetime.combine(filters.created_from, time.min, UTC)
        )
    if filters.created_to is not None:
        end = datetime.combine(filters.created_to + timedelta(days=1), time.min, UTC)
        stmt = stmt.where(Ticket.created_at < end)
    if filters.q and (term := filters.q.strip()):
        conditions = [
            Ticket.title.icontains(term, autoescape=True),
            Ticket.description.icontains(term, autoescape=True),
        ]
        if term.lstrip("#").isdigit():
            conditions.append(Ticket.id == int(term.lstrip("#")))
        stmt = stmt.where(or_(*conditions))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    descending = filters.sort.startswith("-")
    sort_column = _SORT_COLUMNS[filters.sort.lstrip("-")]
    stmt = (
        stmt.order_by(sort_column.desc() if descending else sort_column.asc(), Ticket.id.desc())
        .options(*_TICKET_RELATIONS)
        .offset(filters.offset)
        .limit(filters.page_size)
    )
    return list(db.scalars(stmt)), total


def list_messages(db: Session, actor: User, ticket_id: int) -> list[TicketMessage]:
    ticket = get_ticket(db, actor, ticket_id)
    stmt = (
        select(TicketMessage)
        .where(TicketMessage.ticket_id == ticket.id)
        .options(selectinload(TicketMessage.author))
        .order_by(TicketMessage.created_at, TicketMessage.id)
    )
    if not actor.is_staff:
        stmt = stmt.where(TicketMessage.is_internal.is_(False))
    return list(db.scalars(stmt))


def list_history(db: Session, actor: User, ticket_id: int) -> list[TicketHistory]:
    ticket = get_ticket(db, actor, ticket_id)
    stmt = (
        select(TicketHistory)
        .where(TicketHistory.ticket_id == ticket.id)
        .options(selectinload(TicketHistory.actor))
        .order_by(TicketHistory.created_at, TicketHistory.id)
    )
    return list(db.scalars(stmt))


# --- Commands ------------------------------------------------------------------------------


def create_ticket(db: Session, requester: User, data: TicketCreate) -> Ticket:
    category, subcategory = _resolve_classification(
        db, requester.organization_id, data.category_id, data.subcategory_id, require_active=True
    )
    ticket = Ticket(
        organization_id=requester.organization_id,
        title=data.title,
        description=data.description,
        requester=requester,
        category=category,
        subcategory=subcategory,
    )
    db.add(ticket)
    record_event(db, ticket, requester, TicketEventType.CREATED)
    triage_service.apply_creation_rules(db, ticket)
    db.commit()
    log_event(logger, "ticket.created", ticket_id=ticket.id, user_id=requester.id)
    return get_ticket(db, requester, ticket.id)


def update_ticket(db: Session, actor: User, ticket_id: int, data: TicketUpdate) -> Ticket:
    ticket = get_ticket(db, actor, ticket_id)
    _ensure_not_closed(ticket)
    fields = data.model_fields_set

    if data.title is not None and data.title != ticket.title:
        record_event(
            db, ticket, actor, TicketEventType.TITLE_CHANGED, "title", ticket.title, data.title
        )
        ticket.title = data.title
    if data.description is not None and data.description != ticket.description:
        record_event(db, ticket, actor, TicketEventType.DESCRIPTION_CHANGED, "description")
        ticket.description = data.description
    if data.priority is not None and data.priority != ticket.priority:
        record_event(
            db,
            ticket,
            actor,
            TicketEventType.PRIORITY_CHANGED,
            "priority",
            ticket.priority,
            data.priority,
        )
        ticket.priority = data.priority
    if fields & {"category_id", "subcategory_id"}:
        _apply_classification(db, ticket, actor, data)
    if "team_id" in fields and data.team_id != ticket.team_id:
        team = (
            team_service.get_team(db, actor.organization_id, data.team_id)
            if data.team_id is not None
            else None
        )
        record_event(
            db,
            ticket,
            actor,
            TicketEventType.TEAM_CHANGED,
            "team",
            display_name(ticket.team),
            display_name(team),
        )
        ticket.team = team
    if data.status is not None:
        _change_status(db, ticket, actor, data.status)

    db.commit()
    log_event(
        logger,
        "ticket.updated",
        ticket_id=ticket.id,
        user_id=actor.id,
        fields=",".join(sorted(fields)),
    )
    return ticket


def assign_ticket(db: Session, actor: User, ticket_id: int, assignee_id: int | None) -> Ticket:
    ticket = get_ticket(db, actor, ticket_id)
    _ensure_not_closed(ticket)
    assignee = (
        actor
        if assignee_id is None
        else user_service.get_user(db, actor.organization_id, assignee_id)
    )
    if not assignee.is_staff or not assignee.is_active:
        raise AppError(
            "INVALID_ASSIGNEE", "Tickets can only be assigned to active agents or admins.", 422
        )

    if ticket.assignee_id != assignee.id:
        record_event(
            db,
            ticket,
            actor,
            TicketEventType.ASSIGNEE_CHANGED,
            "assignee",
            ticket.assignee.full_name if ticket.assignee else None,
            assignee.full_name,
        )
        ticket.assignee = assignee
        db.commit()
        log_event(
            logger,
            "ticket.assigned",
            ticket_id=ticket.id,
            assignee_id=assignee.id,
            user_id=actor.id,
        )
    return ticket


def resolve_ticket(db: Session, actor: User, ticket_id: int, data: TicketResolve) -> Ticket:
    ticket = get_ticket(db, actor, ticket_id)
    _ensure_not_closed(ticket)
    if data.resolution:
        db.add(TicketMessage(ticket=ticket, author=actor, body=data.resolution))
        record_event(db, ticket, actor, TicketEventType.COMMENT_ADDED)
    _change_status(db, ticket, actor, TicketStatus.RESOLVED)
    db.commit()
    log_event(logger, "ticket.resolved", ticket_id=ticket.id, user_id=actor.id)
    return ticket


def add_message(db: Session, actor: User, ticket_id: int, data: MessageCreate) -> TicketMessage:
    ticket = get_ticket(db, actor, ticket_id)
    _ensure_not_closed(ticket)
    if data.is_internal and not actor.is_staff:
        raise PermissionDeniedError("Only agents and admins can write internal notes.")

    message = TicketMessage(
        ticket=ticket, author=actor, body=data.body, is_internal=data.is_internal
    )
    db.add(message)
    ticket.updated_at = utcnow()
    record_event(
        db,
        ticket,
        actor,
        TicketEventType.COMMENT_ADDED,
        field="internal_note" if data.is_internal else "message",
    )
    # The requester answered what the agent was waiting for: hand the ticket back to the team.
    if actor.id == ticket.requester_id and ticket.status == TicketStatus.WAITING_USER:
        _change_status(db, ticket, actor, TicketStatus.IN_PROGRESS)

    db.commit()
    log_event(
        logger,
        "ticket.message_created",
        ticket_id=ticket.id,
        message_id=message.id,
        user_id=actor.id,
    )
    return message


def delete_ticket(db: Session, actor: User, ticket_id: int) -> None:
    ticket = get_ticket(db, actor, ticket_id)
    db.delete(ticket)
    db.commit()
    log_event(logger, "ticket.deleted", ticket_id=ticket_id, user_id=actor.id)


# --- Helpers -------------------------------------------------------------------------------


def _ensure_not_closed(ticket: Ticket) -> None:
    if ticket.status == TicketStatus.CLOSED:
        raise AppError("TICKET_CLOSED", "Closed tickets cannot be changed.", 409)


def _change_status(db: Session, ticket: Ticket, actor: User, new_status: TicketStatus) -> None:
    if new_status == ticket.status:
        return
    old_status = ticket.status
    ticket.status = new_status
    if new_status == TicketStatus.RESOLVED:
        ticket.resolved_at = utcnow()
    elif new_status != TicketStatus.CLOSED:
        ticket.resolved_at = None  # reopened

    event = (
        TicketEventType.RESOLVED
        if new_status == TicketStatus.RESOLVED
        else TicketEventType.STATUS_CHANGED
    )
    record_event(db, ticket, actor, event, "status", old_status, new_status)


def _resolve_classification(
    db: Session,
    organization_id: int,
    category_id: int | None,
    subcategory_id: int | None,
    require_active: bool,
) -> tuple[Category | None, Subcategory | None]:
    """Validate a category/subcategory pair. The category is inferred from the subcategory."""
    subcategory = None
    if subcategory_id is not None:
        subcategory = category_service.get_subcategory(db, organization_id, subcategory_id)
        if category_id is None:
            category_id = subcategory.category_id
        elif subcategory.category_id != category_id:
            raise AppError(
                "SUBCATEGORY_MISMATCH",
                "The subcategory does not belong to the selected category.",
                422,
            )

    category = (
        category_service.get_category(db, organization_id, category_id)
        if category_id is not None
        else None
    )
    if require_active and (
        (category is not None and not category.is_active)
        or (subcategory is not None and not subcategory.is_active)
    ):
        raise AppError("CATEGORY_INACTIVE", "The selected category is no longer available.", 422)
    return category, subcategory


def _apply_classification(db: Session, ticket: Ticket, actor: User, data: TicketUpdate) -> None:
    fields = data.model_fields_set
    category_id = ticket.category_id
    subcategory_id = ticket.subcategory_id

    if "category_id" in fields:
        category_id = data.category_id
        if category_id != ticket.category_id:
            subcategory_id = None  # the old subcategory belongs to the old category
    if "subcategory_id" in fields:
        subcategory_id = data.subcategory_id
        if subcategory_id is not None and "category_id" not in fields:
            category_id = None  # infer from the new subcategory

    category, subcategory = _resolve_classification(
        db, actor.organization_id, category_id, subcategory_id, require_active=False
    )
    if category is not ticket.category:
        record_event(
            db,
            ticket,
            actor,
            TicketEventType.CATEGORY_CHANGED,
            "category",
            display_name(ticket.category),
            display_name(category),
        )
        ticket.category = category
    if subcategory is not ticket.subcategory:
        record_event(
            db,
            ticket,
            actor,
            TicketEventType.SUBCATEGORY_CHANGED,
            "subcategory",
            display_name(ticket.subcategory),
            display_name(subcategory),
        )
        ticket.subcategory = subcategory
