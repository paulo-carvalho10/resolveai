"""Requesters who solve the problem themselves, and replies that reopen a resolved ticket."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models import User
from tests.conftest import auth_headers

PRINTER_TICKET = {
    "title": "Impressora fiscal não imprime",
    "description": "A impressora do caixa 2 parou de imprimir os cupons desde cedo.",
}
SOLUTION = "Reiniciei o serviço de spooler do Windows e a impressora voltou a imprimir."


@pytest.fixture(autouse=True)
def _no_ai_on_create(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_analyze_on_create", False)
    monkeypatch.setattr(get_settings(), "ai_suggest_on_create", False)


def open_ticket(client: TestClient, requester: User) -> int:
    response = client.post("/tickets", json=PRINTER_TICKET, headers=auth_headers(requester))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def get(client: TestClient, user: User, path: str) -> Any:
    response = client.get(path, headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()


def self_resolve(client: TestClient, user: User, ticket_id: int, solution: str = SOLUTION) -> Any:
    return client.post(
        f"/tickets/{ticket_id}/self-resolve",
        json={"solution": solution},
        headers=auth_headers(user),
    )


def reply(client: TestClient, user: User, ticket_id: int, **extra: object) -> None:
    response = client.post(
        f"/tickets/{ticket_id}/messages",
        json={"body": "O problema voltou hoje de manhã.", **extra},
        headers=auth_headers(user),
    )
    assert response.status_code == 201, response.text


# --- Solving it themselves -----------------------------------------------------------------


@pytest.mark.parametrize("status", ["OPEN", "IN_PROGRESS", "WAITING_USER"])
def test_requester_resolves_their_ticket_and_explains_how(
    client: TestClient, requester: User, agent: User, status: str
) -> None:
    ticket_id = open_ticket(client, requester)
    client.patch(f"/tickets/{ticket_id}", json={"status": status}, headers=auth_headers(agent))

    response = self_resolve(client, requester, ticket_id)

    assert response.status_code == 200, response.text
    ticket = response.json()
    assert ticket["status"] == "RESOLVED"
    assert ticket["resolved_by"]["id"] == requester.id
    assert ticket["auto_close_at"] is not None

    # The team reads the solution in the conversation, flagged for review.
    messages = get(client, agent, f"/tickets/{ticket_id}/messages")
    solution = messages[-1]
    assert (solution["body"], solution["is_solution"]) == (SOLUTION, True)
    assert solution["author"]["id"] == requester.id

    history = get(client, agent, f"/tickets/{ticket_id}/history")
    assert history[-1]["event_type"] == "RESOLVED_BY_REQUESTER"
    assert history[-1]["actor"]["id"] == requester.id


@pytest.mark.parametrize("solution", ["", "   ", "resolvi"])
def test_requester_must_say_how_they_solved_it(
    client: TestClient, requester: User, solution: str
) -> None:
    ticket_id = open_ticket(client, requester)

    response = self_resolve(client, requester, ticket_id, solution)

    assert response.status_code == 422
    assert get(client, requester, f"/tickets/{ticket_id}")["status"] == "OPEN"


def test_only_the_requester_can_report_solving_it(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket_id = open_ticket(client, requester)

    response = self_resolve(client, agent, ticket_id)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_already_resolved_or_closed_tickets_cannot_be_self_resolved(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket_id = open_ticket(client, requester)
    client.post(f"/tickets/{ticket_id}/resolve", json={}, headers=auth_headers(agent))

    already = self_resolve(client, requester, ticket_id)
    assert already.status_code == 409
    assert already.json()["error"]["code"] == "TICKET_ALREADY_RESOLVED"

    client.post(f"/tickets/{ticket_id}/close", headers=auth_headers(requester))
    closed = self_resolve(client, requester, ticket_id)
    assert closed.status_code == 409
    assert closed.json()["error"]["code"] == "TICKET_CLOSED"


def test_team_resolution_records_who_resolved(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket_id = open_ticket(client, requester)

    response = client.post(f"/tickets/{ticket_id}/resolve", json={}, headers=auth_headers(agent))

    assert response.json()["resolved_by"]["id"] == agent.id


def test_team_can_list_tickets_solved_by_their_requesters(
    client: TestClient, requester: User, agent: User
) -> None:
    solved_alone = open_ticket(client, requester)
    self_resolve(client, requester, solved_alone)
    solved_by_team = open_ticket(client, requester)
    client.post(f"/tickets/{solved_by_team}/resolve", json={}, headers=auth_headers(agent))
    open_ticket(client, requester)

    page = get(client, agent, "/tickets?resolved_by_requester=true")

    assert [ticket["id"] for ticket in page["items"]] == [solved_alone]


# --- Replies reopen resolved tickets -------------------------------------------------------


def test_requester_reply_puts_a_resolved_ticket_back_in_the_queue(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket_id = open_ticket(client, requester)
    client.post(f"/tickets/{ticket_id}/resolve", json={}, headers=auth_headers(agent))

    reply(client, requester, ticket_id)

    ticket = get(client, agent, f"/tickets/{ticket_id}")
    assert ticket["status"] == "OPEN"  # nobody was assigned, so it waits for someone to take it
    assert ticket["resolved_at"] is None
    assert ticket["resolved_by"] is None
    assert ticket["auto_close_at"] is None

    history = get(client, agent, f"/tickets/{ticket_id}/history")
    reopening = history[-1]
    assert reopening["event_type"] == "STATUS_CHANGED"
    assert (reopening["old_value"], reopening["new_value"]) == ("RESOLVED", "OPEN")
    assert reopening["actor"]["id"] == requester.id


def test_reopened_ticket_goes_back_to_whoever_was_working_on_it(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket_id = open_ticket(client, requester)
    client.post(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers(agent))
    client.post(f"/tickets/{ticket_id}/resolve", json={}, headers=auth_headers(agent))

    reply(client, requester, ticket_id)

    ticket = get(client, agent, f"/tickets/{ticket_id}")
    assert ticket["status"] == "IN_PROGRESS"
    assert ticket["assignee"]["id"] == agent.id


def test_a_workaround_that_stops_working_reopens_the_ticket(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket_id = open_ticket(client, requester)
    self_resolve(client, requester, ticket_id)

    reply(client, requester, ticket_id)

    assert get(client, agent, f"/tickets/{ticket_id}")["status"] == "OPEN"
    # The solution the requester described stays in the conversation.
    messages = get(client, agent, f"/tickets/{ticket_id}/messages")
    assert [message["is_solution"] for message in messages] == [True, False]
    assert get(client, agent, "/tickets?resolved_by_requester=true")["items"] == []


@pytest.mark.parametrize("is_internal", [False, True])
def test_team_messages_do_not_reopen_a_resolved_ticket(
    client: TestClient, requester: User, agent: User, is_internal: bool
) -> None:
    ticket_id = open_ticket(client, requester)
    client.post(f"/tickets/{ticket_id}/resolve", json={}, headers=auth_headers(agent))

    reply(client, agent, ticket_id, is_internal=is_internal)

    assert get(client, agent, f"/tickets/{ticket_id}")["status"] == "RESOLVED"
