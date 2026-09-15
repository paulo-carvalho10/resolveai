from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import TicketPriority, TicketStatus, User
from app.services import sla
from app.services.sla import SlaStatus
from tests.conftest import auth_headers

CREATED = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def test_critical_ticket_has_1h_sla() -> None:
    assert sla.due_at(TicketPriority.CRITICAL, CREATED) == CREATED + timedelta(hours=1)


@pytest.mark.parametrize(
    ("priority", "hours"),
    [
        (TicketPriority.LOW, 24),
        (TicketPriority.MEDIUM, 8),
        (TicketPriority.HIGH, 4),
        (TicketPriority.CRITICAL, 1),
    ],
)
def test_targets_per_priority(priority: TicketPriority, hours: int) -> None:
    assert sla.target(priority) == timedelta(hours=hours)


@pytest.mark.parametrize(
    ("minutes_after", "resolved_minutes", "status", "expected"),
    [
        (100, None, TicketStatus.OPEN, SlaStatus.ON_TRACK),  # 140 of 240 min left
        (190, None, TicketStatus.IN_PROGRESS, SlaStatus.AT_RISK),  # 50 min left < 25%
        (241, None, TicketStatus.WAITING_USER, SlaStatus.BREACHED),
        (500, 239, TicketStatus.RESOLVED, SlaStatus.MET),
        (500, 241, TicketStatus.RESOLVED, SlaStatus.BREACHED),
        (500, None, TicketStatus.CLOSED, SlaStatus.MET),  # closed without resolution
    ],
)
def test_status_against_a_4h_target(
    minutes_after: int, resolved_minutes: int | None, status: TicketStatus, expected: SlaStatus
) -> None:
    now = CREATED + timedelta(minutes=minutes_after)
    resolved = CREATED + timedelta(minutes=resolved_minutes) if resolved_minutes else None

    assert sla.status(TicketPriority.HIGH, status, CREATED, resolved, now) == expected


def test_ticket_response_includes_sla(client: TestClient, requester: User) -> None:
    response = client.post(
        "/tickets",
        json={"title": "Sistema lento", "description": "As telas demoram para abrir."},
        headers=auth_headers(requester),
    )

    ticket = response.json()
    created = datetime.fromisoformat(ticket["created_at"])
    assert datetime.fromisoformat(ticket["sla_due_at"]) == created + timedelta(hours=8)
    assert ticket["sla_status"] == "ON_TRACK"
