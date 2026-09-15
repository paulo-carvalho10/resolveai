from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ticket, TicketEventType, TicketHistory, User


def record_event(
    db: Session,
    ticket: Ticket,
    actor: User | None,
    event_type: TicketEventType,
    field: str | None = None,
    old_value: object = None,
    new_value: object = None,
) -> None:
    """Append an audit entry. `actor=None` means the system (rules or AI) made the change."""
    db.add(
        TicketHistory(
            ticket=ticket,
            actor=actor,
            event_type=event_type,
            field=field,
            old_value=None if old_value is None else str(old_value),
            new_value=None if new_value is None else str(new_value),
        )
    )


def display_name(entity: Any) -> str | None:
    return entity.name if entity is not None else None


def fields_changed_by_humans(db: Session, ticket: Ticket) -> set[str]:
    """Ticket fields a person has edited. Automation must never overwrite these."""
    if ticket.id is None:
        return set()
    stmt = select(TicketHistory.field).where(
        TicketHistory.ticket_id == ticket.id,
        TicketHistory.actor_id.is_not(None),
        TicketHistory.field.is_not(None),
        TicketHistory.event_type.in_(
            [
                TicketEventType.CATEGORY_CHANGED,
                TicketEventType.SUBCATEGORY_CHANGED,
                TicketEventType.PRIORITY_CHANGED,
                TicketEventType.TEAM_CHANGED,
            ]
        ),
    )
    return {field for field in db.scalars(stmt) if field is not None}
