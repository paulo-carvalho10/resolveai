"""SLA: resolution deadline by priority, and where a ticket stands against it.

The deadline counts from creation with the ticket's current priority. Pausing the clock while
waiting for the requester is not modeled yet.
"""

from datetime import datetime, timedelta
from enum import StrEnum

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.enums import TicketPriority, TicketStatus


class SlaStatus(StrEnum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"
    MET = "MET"


def target(priority: TicketPriority) -> timedelta:
    settings = get_settings()
    hours = {
        TicketPriority.LOW: settings.sla_hours_low,
        TicketPriority.MEDIUM: settings.sla_hours_medium,
        TicketPriority.HIGH: settings.sla_hours_high,
        TicketPriority.CRITICAL: settings.sla_hours_critical,
    }[priority]
    return timedelta(hours=hours)


def due_at(priority: TicketPriority, created_at: datetime) -> datetime:
    return created_at + target(priority)


def status(
    priority: TicketPriority,
    ticket_status: TicketStatus,
    created_at: datetime,
    resolved_at: datetime | None,
    now: datetime | None = None,
) -> SlaStatus:
    deadline = due_at(priority, created_at)
    if resolved_at is not None:
        return SlaStatus.MET if resolved_at <= deadline else SlaStatus.BREACHED
    if ticket_status == TicketStatus.CLOSED:
        # Closed without a resolution (e.g. duplicate): nothing left to measure.
        return SlaStatus.MET

    remaining = deadline - (now or utcnow())
    if remaining < timedelta(0):
        return SlaStatus.BREACHED
    if remaining <= target(priority) * get_settings().sla_at_risk_ratio:
        return SlaStatus.AT_RISK
    return SlaStatus.ON_TRACK
