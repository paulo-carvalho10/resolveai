"""Closing tickets: by the requester, by the team, and by the system after staying resolved."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_session_factory
from app.core.config import get_settings
from app.main import app
from app.models import (
    Organization,
    Ticket,
    TicketEventType,
    TicketHistory,
    TicketStatus,
    User,
    UserRole,
)
from app.models.base import utcnow
from app.services import ticket_service
from tests.conftest import auth_headers

BILLING_TICKET = {
    "title": "Boleto gerado com vencimento errado",
    "description": "O boleto do pedido 1234 saiu com a data de ontem.",
}


@pytest.fixture(autouse=True)
def _no_ai_on_create(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_analyze_on_create", False)
    monkeypatch.setattr(get_settings(), "ai_suggest_on_create", False)


def open_ticket(client: TestClient, requester: User) -> int:
    response = client.post("/tickets", json=BILLING_TICKET, headers=auth_headers(requester))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def resolve(client: TestClient, agent: User, ticket_id: int) -> dict:
    response = client.post(f"/tickets/{ticket_id}/resolve", json={}, headers=auth_headers(agent))
    assert response.status_code == 200, response.text
    return response.json()


def close(client: TestClient, user: User, ticket_id: int) -> Any:
    return client.post(f"/tickets/{ticket_id}/close", headers=auth_headers(user))


# --- Closing by hand -----------------------------------------------------------------------


def test_requester_closes_a_resolved_ticket(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket_id = open_ticket(client, requester)
    resolved = resolve(client, agent, ticket_id)

    response = close(client, requester, ticket_id)

    assert response.status_code == 200, response.text
    ticket = response.json()
    assert ticket["status"] == "CLOSED"
    assert ticket["resolved_at"] == resolved["resolved_at"]  # the SLA keeps its resolution time
    assert ticket["sla_status"] == "MET"
    assert ticket["auto_close_at"] is None

    history = client.get(f"/tickets/{ticket_id}/history", headers=auth_headers(agent)).json()
    closing = history[-1]
    assert closing["event_type"] == "STATUS_CHANGED"
    assert (closing["old_value"], closing["new_value"]) == ("RESOLVED", "CLOSED")
    assert closing["actor"]["id"] == requester.id


@pytest.mark.parametrize("status", ["OPEN", "IN_PROGRESS", "WAITING_USER"])
def test_requester_cannot_close_before_the_ticket_is_resolved(
    client: TestClient, requester: User, agent: User, status: str
) -> None:
    ticket_id = open_ticket(client, requester)
    client.patch(f"/tickets/{ticket_id}", json={"status": status}, headers=auth_headers(agent))

    response = close(client, requester, ticket_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TICKET_NOT_RESOLVED"


def test_requester_cannot_close_someone_elses_ticket(
    client: TestClient,
    requester: User,
    agent: User,
    make_user: Callable[..., User],
    org: Organization,
) -> None:
    ticket_id = open_ticket(client, requester)
    resolve(client, agent, ticket_id)
    stranger = make_user(org, UserRole.USER)

    response = close(client, stranger, ticket_id)

    assert response.status_code == 404


def test_team_can_close_a_ticket_that_was_never_resolved(
    client: TestClient, requester: User, agent: User
) -> None:
    """Duplicates and spam are closed straight away, without a resolution."""
    ticket_id = open_ticket(client, requester)

    response = close(client, agent, ticket_id)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CLOSED"
    assert response.json()["resolved_at"] is None


def test_closed_ticket_cannot_be_closed_again(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket_id = open_ticket(client, requester)
    resolve(client, agent, ticket_id)
    close(client, requester, ticket_id)

    response = close(client, agent, ticket_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TICKET_CLOSED"


def test_resolved_ticket_says_when_it_will_close_on_its_own(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket_id = open_ticket(client, requester)
    opened = client.get(f"/tickets/{ticket_id}", headers=auth_headers(requester)).json()
    assert opened["auto_close_at"] is None

    resolved = resolve(client, agent, ticket_id)
    window = datetime.fromisoformat(resolved["auto_close_at"]) - datetime.fromisoformat(
        resolved["resolved_at"]
    )
    assert window == timedelta(days=5)

    reopened = client.patch(
        f"/tickets/{ticket_id}", json={"status": "IN_PROGRESS"}, headers=auth_headers(agent)
    ).json()
    assert reopened["auto_close_at"] is None


# --- Closing automatically -----------------------------------------------------------------


def add_ticket(
    db: Session,
    org: Organization,
    requester: User,
    *,
    resolved_days_ago: float | None,
    now: datetime,
    status: TicketStatus = TicketStatus.RESOLVED,
) -> Ticket:
    ticket = Ticket(
        organization_id=org.id,
        title=BILLING_TICKET["title"],
        description=BILLING_TICKET["description"],
        requester_id=requester.id,
        status=status,
        created_at=now - timedelta(days=30),
        resolved_at=None if resolved_days_ago is None else now - timedelta(days=resolved_days_ago),
    )
    db.add(ticket)
    db.commit()
    return ticket


def current_status(db: Session, ticket: Ticket) -> TicketStatus:
    return db.scalars(select(Ticket.status).where(Ticket.id == ticket.id)).one()


def test_auto_close_only_touches_tickets_resolved_long_enough(
    db: Session, org: Organization, requester: User
) -> None:
    now = utcnow()
    overdue = add_ticket(db, org, requester, resolved_days_ago=6, now=now)
    on_the_deadline = add_ticket(db, org, requester, resolved_days_ago=5, now=now)
    recent = add_ticket(db, org, requester, resolved_days_ago=4.9, now=now)
    in_progress = add_ticket(
        db, org, requester, resolved_days_ago=None, now=now, status=TicketStatus.IN_PROGRESS
    )

    assert ticket_service.close_stale_resolved_tickets(db, now=now) == 2

    assert current_status(db, overdue) == TicketStatus.CLOSED
    assert current_status(db, on_the_deadline) == TicketStatus.CLOSED
    assert current_status(db, recent) == TicketStatus.RESOLVED
    assert current_status(db, in_progress) == TicketStatus.IN_PROGRESS

    entry = db.scalars(select(TicketHistory).where(TicketHistory.ticket_id == overdue.id)).one()
    assert entry.event_type == TicketEventType.AUTO_CLOSED
    assert entry.actor_id is None  # the system did it
    assert (entry.old_value, entry.new_value) == ("RESOLVED", "CLOSED")

    # Running again changes nothing and logs nothing twice.
    assert ticket_service.close_stale_resolved_tickets(db, now=now) == 0
    assert len(db.scalars(select(TicketHistory)).all()) == 2


def test_auto_close_follows_the_configured_window(
    db: Session, org: Organization, requester: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "auto_close_resolved_days", 10)
    now = utcnow()
    add_ticket(db, org, requester, resolved_days_ago=6, now=now)

    assert ticket_service.close_stale_resolved_tickets(db, now=now) == 0


def test_auto_close_handles_more_tickets_than_one_batch(
    db: Session, org: Organization, requester: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ticket_service, "AUTO_CLOSE_BATCH_SIZE", 2)
    now = utcnow()
    for _ in range(5):
        add_ticket(db, org, requester, resolved_days_ago=8, now=now)

    assert ticket_service.close_stale_resolved_tickets(db, now=now) == 5
    assert set(db.scalars(select(Ticket.status))) == {TicketStatus.CLOSED}
    assert len(db.scalars(select(TicketHistory)).all()) == 5


# --- The job inside the API ----------------------------------------------------------------


def test_api_closes_overdue_tickets_at_startup(
    session_factory: sessionmaker[Session],
    db: Session,
    org: Organization,
    requester: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sleeping host can miss a deadline: the API catches up before serving requests."""
    ticket = add_ticket(db, org, requester, resolved_days_ago=7, now=utcnow())
    monkeypatch.setattr(get_settings(), "auto_close_interval_minutes", 60)
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    try:
        with TestClient(app):
            assert current_status(db, ticket) == TicketStatus.CLOSED
    finally:
        app.dependency_overrides.clear()


def test_api_starts_even_when_the_job_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable_database() -> Session:
        raise ConnectionError("database is down")

    monkeypatch.setattr(get_settings(), "auto_close_interval_minutes", 60)
    app.dependency_overrides[get_session_factory] = lambda: unreachable_database
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
    finally:
        app.dependency_overrides.clear()
