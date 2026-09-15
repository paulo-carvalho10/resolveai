from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Organization, Ticket, User, UserRole
from tests.conftest import auth_headers

NFE_TICKET = {
    "title": "Não consigo emitir NF-e",
    "description": "O sistema apresenta rejeição 539 ao transmitir a nota.",
}


@pytest.fixture
def fiscal(client: TestClient, admin: User) -> dict:
    response = client.post(
        "/categories",
        json={"name": "Fiscal", "subcategories": [{"name": "NF-e"}, {"name": "NFS-e"}]},
        headers=auth_headers(admin),
    )
    return response.json()


@pytest.fixture
def infra(client: TestClient, admin: User) -> dict:
    response = client.post(
        "/categories",
        json={"name": "Infraestrutura", "subcategories": [{"name": "VPN"}]},
        headers=auth_headers(admin),
    )
    return response.json()


def open_ticket(client: TestClient, user: User, **overrides: object) -> dict:
    response = client.post("/tickets", json={**NFE_TICKET, **overrides}, headers=auth_headers(user))
    assert response.status_code == 201, response.text
    return response.json()


def history_events(client: TestClient, staff: User, ticket_id: int) -> list[str]:
    response = client.get(f"/tickets/{ticket_id}/history", headers=auth_headers(staff))
    return [entry["event_type"] for entry in response.json()]


# --- Creation ------------------------------------------------------------------------------


def test_create_ticket(client: TestClient, requester: User, agent: User) -> None:
    ticket = open_ticket(client, requester)

    assert ticket["status"] == "OPEN"
    assert ticket["priority"] == "MEDIUM"
    assert ticket["requester"]["id"] == requester.id
    assert ticket["assignee"] is None
    assert ticket["resolved_at"] is None
    assert history_events(client, agent, ticket["id"]) == ["CREATED"]


def test_create_ticket_infers_category_from_subcategory(
    client: TestClient, requester: User, fiscal: dict
) -> None:
    nfe = fiscal["subcategories"][0]
    ticket = open_ticket(client, requester, subcategory_id=nfe["id"])

    assert ticket["category"] == {"id": fiscal["id"], "name": "Fiscal"}
    assert ticket["subcategory"] == {"id": nfe["id"], "name": "NF-e"}


def test_create_ticket_rejects_subcategory_from_other_category(
    client: TestClient, requester: User, fiscal: dict, infra: dict
) -> None:
    response = client.post(
        "/tickets",
        json={
            **NFE_TICKET,
            "category_id": fiscal["id"],
            "subcategory_id": infra["subcategories"][0]["id"],
        },
        headers=auth_headers(requester),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SUBCATEGORY_MISMATCH"


def test_create_ticket_rejects_inactive_category(
    client: TestClient, admin: User, requester: User, fiscal: dict
) -> None:
    client.patch(
        f"/categories/{fiscal['id']}", json={"is_active": False}, headers=auth_headers(admin)
    )
    response = client.post(
        "/tickets",
        json={**NFE_TICKET, "category_id": fiscal["id"]},
        headers=auth_headers(requester),
    )
    assert response.json()["error"]["code"] == "CATEGORY_INACTIVE"


def test_create_ticket_validates_input(client: TestClient, requester: User) -> None:
    response = client.post(
        "/tickets", json={"title": "Hi", "description": "short"}, headers=auth_headers(requester)
    )
    assert response.status_code == 422
    fields = {detail["field"] for detail in response.json()["error"]["details"]}
    assert fields == {"body.title", "body.description"}


def test_create_ticket_requires_authentication(client: TestClient) -> None:
    assert client.post("/tickets", json=NFE_TICKET).status_code == 401


# --- Visibility ----------------------------------------------------------------------------


def test_requester_only_sees_own_tickets(
    client: TestClient,
    make_user: Callable[..., User],
    org: Organization,
    requester: User,
    agent: User,
) -> None:
    colleague = make_user(org, UserRole.USER)
    mine = open_ticket(client, requester)
    theirs = open_ticket(client, colleague)

    listed = client.get("/tickets", headers=auth_headers(requester)).json()
    assert [t["id"] for t in listed["items"]] == [mine["id"]]

    # Filtering by someone else's id must not widen what a requester can see.
    spoofed = client.get(
        "/tickets", params={"requester_id": colleague.id}, headers=auth_headers(requester)
    ).json()
    assert [t["id"] for t in spoofed["items"]] == [mine["id"]]

    response = client.get(f"/tickets/{theirs['id']}", headers=auth_headers(requester))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"

    assert client.get("/tickets", headers=auth_headers(agent)).json()["total"] == 2


def test_tickets_are_isolated_between_organizations(
    client: TestClient, requester: User, other_admin: User
) -> None:
    ticket = open_ticket(client, requester)

    assert (
        client.get(f"/tickets/{ticket['id']}", headers=auth_headers(other_admin)).status_code == 404
    )
    assert client.get("/tickets", headers=auth_headers(other_admin)).json()["total"] == 0
    response = client.patch(
        f"/tickets/{ticket['id']}", json={"priority": "LOW"}, headers=auth_headers(other_admin)
    )
    assert response.status_code == 404


# --- Triage --------------------------------------------------------------------------------


def test_agent_can_triage_ticket_and_history_is_recorded(
    client: TestClient, requester: User, agent: User, admin: User, fiscal: dict
) -> None:
    team = client.post("/teams", json={"name": "ERP Fiscal"}, headers=auth_headers(admin)).json()
    ticket = open_ticket(client, requester)

    response = client.patch(
        f"/tickets/{ticket['id']}",
        json={
            "priority": "HIGH",
            "subcategory_id": fiscal["subcategories"][0]["id"],
            "team_id": team["id"],
            "status": "IN_PROGRESS",
        },
        headers=auth_headers(agent),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["priority"] == "HIGH"
    assert body["category"]["name"] == "Fiscal"
    assert body["subcategory"]["name"] == "NF-e"
    assert body["team"]["name"] == "ERP Fiscal"
    assert body["status"] == "IN_PROGRESS"

    history = client.get(f"/tickets/{ticket['id']}/history", headers=auth_headers(agent)).json()
    changes = {entry["field"]: (entry["old_value"], entry["new_value"]) for entry in history[1:]}
    assert changes == {
        "priority": ("MEDIUM", "HIGH"),
        "category": (None, "Fiscal"),
        "subcategory": (None, "NF-e"),
        "team": (None, "ERP Fiscal"),
        "status": ("OPEN", "IN_PROGRESS"),
    }
    assert all(entry["actor"]["id"] == agent.id for entry in history[1:])


def test_changing_category_clears_subcategory_from_old_category(
    client: TestClient, requester: User, agent: User, fiscal: dict, infra: dict
) -> None:
    ticket = open_ticket(client, requester, subcategory_id=fiscal["subcategories"][0]["id"])

    response = client.patch(
        f"/tickets/{ticket['id']}", json={"category_id": infra["id"]}, headers=auth_headers(agent)
    )
    assert response.json()["category"]["name"] == "Infraestrutura"
    assert response.json()["subcategory"] is None


def test_null_clears_team_but_omitted_field_is_kept(
    client: TestClient, requester: User, agent: User, admin: User
) -> None:
    team = client.post("/teams", json={"name": "Infra"}, headers=auth_headers(admin)).json()
    ticket = open_ticket(client, requester)
    client.patch(
        f"/tickets/{ticket['id']}", json={"team_id": team["id"]}, headers=auth_headers(agent)
    )

    kept = client.patch(
        f"/tickets/{ticket['id']}", json={"priority": "LOW"}, headers=auth_headers(agent)
    )
    assert kept.json()["team"]["id"] == team["id"]

    cleared = client.patch(
        f"/tickets/{ticket['id']}", json={"team_id": None}, headers=auth_headers(agent)
    )
    assert cleared.json()["team"] is None


def test_user_cannot_update_ticket(client: TestClient, requester: User) -> None:
    ticket = open_ticket(client, requester)
    response = client.patch(
        f"/tickets/{ticket['id']}", json={"priority": "CRITICAL"}, headers=auth_headers(requester)
    )
    assert response.status_code == 403


# --- Assignment ----------------------------------------------------------------------------


def test_agent_can_assign_ticket_to_self(client: TestClient, requester: User, agent: User) -> None:
    ticket = open_ticket(client, requester)

    response = client.post(f"/tickets/{ticket['id']}/assign", json={}, headers=auth_headers(agent))

    assert response.status_code == 200
    assert response.json()["assignee"]["id"] == agent.id
    history = client.get(f"/tickets/{ticket['id']}/history", headers=auth_headers(agent)).json()
    assert history[-1]["event_type"] == "ASSIGNEE_CHANGED"
    assert history[-1]["new_value"] == "Maria Agent"


def test_admin_can_assign_ticket_to_agent(
    client: TestClient, requester: User, agent: User, admin: User
) -> None:
    ticket = open_ticket(client, requester)
    response = client.post(
        f"/tickets/{ticket['id']}/assign",
        json={"assignee_id": agent.id},
        headers=auth_headers(admin),
    )
    assert response.json()["assignee"]["id"] == agent.id


def test_ticket_cannot_be_assigned_to_requester_role(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket = open_ticket(client, requester)
    response = client.post(
        f"/tickets/{ticket['id']}/assign",
        json={"assignee_id": requester.id},
        headers=auth_headers(agent),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ASSIGNEE"


def test_user_cannot_assign_ticket(client: TestClient, requester: User) -> None:
    ticket = open_ticket(client, requester)
    response = client.post(
        f"/tickets/{ticket['id']}/assign", json={}, headers=auth_headers(requester)
    )
    assert response.status_code == 403


# --- Status lifecycle ----------------------------------------------------------------------


def test_resolve_ticket_sets_resolved_at_and_posts_resolution(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket = open_ticket(client, requester)

    response = client.post(
        f"/tickets/{ticket['id']}/resolve",
        json={"resolution": "Havia uma NF-e autorizada com a mesma numeração."},
        headers=auth_headers(agent),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "RESOLVED"
    assert response.json()["resolved_at"] is not None

    messages = client.get(
        f"/tickets/{ticket['id']}/messages", headers=auth_headers(requester)
    ).json()
    assert messages[0]["body"].startswith("Havia uma NF-e")
    assert history_events(client, agent, ticket["id"]) == ["CREATED", "COMMENT_ADDED", "RESOLVED"]


def test_reopening_ticket_clears_resolved_at(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket = open_ticket(client, requester)
    client.post(f"/tickets/{ticket['id']}/resolve", json={}, headers=auth_headers(agent))

    response = client.patch(
        f"/tickets/{ticket['id']}", json={"status": "IN_PROGRESS"}, headers=auth_headers(agent)
    )
    assert response.json()["resolved_at"] is None


def test_closed_ticket_cannot_be_changed(client: TestClient, requester: User, agent: User) -> None:
    ticket = open_ticket(client, requester)
    client.post(f"/tickets/{ticket['id']}/resolve", json={}, headers=auth_headers(agent))
    closed = client.patch(
        f"/tickets/{ticket['id']}", json={"status": "CLOSED"}, headers=auth_headers(agent)
    )
    assert closed.json()["resolved_at"] is not None

    for response in (
        client.patch(
            f"/tickets/{ticket['id']}", json={"status": "OPEN"}, headers=auth_headers(agent)
        ),
        client.post(f"/tickets/{ticket['id']}/assign", json={}, headers=auth_headers(agent)),
        client.post(
            f"/tickets/{ticket['id']}/messages",
            json={"body": "Still broken"},
            headers=auth_headers(requester),
        ),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "TICKET_CLOSED"


# --- Conversation --------------------------------------------------------------------------


def test_internal_notes_are_hidden_from_requester(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket = open_ticket(client, requester)
    url = f"/tickets/{ticket['id']}/messages"
    client.post(url, json={"body": "Pode enviar o XML da nota?"}, headers=auth_headers(agent))
    client.post(
        url,
        json={"body": "Cliente sem certificado", "is_internal": True},
        headers=auth_headers(agent),
    )

    requester_view = client.get(url, headers=auth_headers(requester)).json()
    agent_view = client.get(url, headers=auth_headers(agent)).json()

    assert [m["body"] for m in requester_view] == ["Pode enviar o XML da nota?"]
    assert len(agent_view) == 2


def test_requester_cannot_write_internal_note(client: TestClient, requester: User) -> None:
    ticket = open_ticket(client, requester)
    response = client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"body": "secret", "is_internal": True},
        headers=auth_headers(requester),
    )
    assert response.status_code == 403


def test_requester_reply_moves_waiting_ticket_back_to_in_progress(
    client: TestClient, requester: User, agent: User
) -> None:
    ticket = open_ticket(client, requester)
    client.patch(
        f"/tickets/{ticket['id']}", json={"status": "WAITING_USER"}, headers=auth_headers(agent)
    )

    client.post(
        f"/tickets/{ticket['id']}/messages",
        json={"body": "XML em anexo"},
        headers=auth_headers(requester),
    )

    detail = client.get(f"/tickets/{ticket['id']}", headers=auth_headers(requester)).json()
    assert detail["status"] == "IN_PROGRESS"


def test_requester_cannot_see_history(client: TestClient, requester: User) -> None:
    ticket = open_ticket(client, requester)
    assert (
        client.get(f"/tickets/{ticket['id']}/history", headers=auth_headers(requester)).status_code
        == 403
    )


# --- Deletion ------------------------------------------------------------------------------


def test_user_cannot_delete_ticket(client: TestClient, requester: User, agent: User) -> None:
    ticket = open_ticket(client, requester)

    assert (
        client.delete(f"/tickets/{ticket['id']}", headers=auth_headers(requester)).status_code
        == 403
    )
    assert client.delete(f"/tickets/{ticket['id']}", headers=auth_headers(agent)).status_code == 403


def test_admin_can_delete_ticket(client: TestClient, requester: User, admin: User) -> None:
    ticket = open_ticket(client, requester)
    client.post(
        f"/tickets/{ticket['id']}/messages", json={"body": "hello"}, headers=auth_headers(requester)
    )

    assert client.delete(f"/tickets/{ticket['id']}", headers=auth_headers(admin)).status_code == 204
    assert client.get(f"/tickets/{ticket['id']}", headers=auth_headers(admin)).status_code == 404


# --- Search --------------------------------------------------------------------------------


def test_list_filters_search_sort_and_paginate(
    client: TestClient, db: Session, requester: User, agent: User, fiscal: dict
) -> None:
    nfe = open_ticket(client, requester, category_id=fiscal["id"])
    vpn = open_ticket(
        client, requester, title="VPN caiu", description="Ninguém consegue acessar a VPN."
    )
    printer = open_ticket(
        client,
        requester,
        title="Impressora parada",
        description="A impressora do financeiro travou.",
    )
    client.patch(
        f"/tickets/{vpn['id']}", json={"priority": "CRITICAL"}, headers=auth_headers(agent)
    )
    client.patch(f"/tickets/{printer['id']}", json={"priority": "LOW"}, headers=auth_headers(agent))
    client.post(f"/tickets/{printer['id']}/assign", json={}, headers=auth_headers(agent))

    old = db.get(Ticket, nfe["id"])
    assert old is not None
    old.created_at = datetime.now(UTC) - timedelta(days=10)
    db.commit()

    def ids(**params: object) -> list[int]:
        response = client.get("/tickets", params=params, headers=auth_headers(agent))
        assert response.status_code == 200, response.text
        return [t["id"] for t in response.json()["items"]]

    assert ids(q="rejeição 539") == [nfe["id"]]
    assert ids(q=f"#{vpn['id']}") == [vpn["id"]]
    assert ids(q="100%") == []
    assert ids(category_id=fiscal["id"]) == [nfe["id"]]
    assert ids(priority=["CRITICAL", "LOW"], sort="-priority") == [vpn["id"], printer["id"]]
    assert ids(sort="priority") == [printer["id"], nfe["id"], vpn["id"]]
    assert ids(assignee_id=agent.id) == [printer["id"]]
    assert set(ids(unassigned=True)) == {nfe["id"], vpn["id"]}
    assert ids(status="RESOLVED") == []
    assert set(ids(created_from=(datetime.now(UTC) - timedelta(days=1)).date().isoformat())) == {
        vpn["id"],
        printer["id"],
    }
    assert ids(created_to=(datetime.now(UTC) - timedelta(days=5)).date().isoformat()) == [nfe["id"]]

    page = client.get(
        "/tickets", params={"page": 2, "page_size": 2}, headers=auth_headers(agent)
    ).json()
    assert page["total"] == 3
    assert page["page"] == 2
    assert [t["id"] for t in page["items"]] == [nfe["id"]]


def test_list_rejects_unknown_filters(client: TestClient, agent: User) -> None:
    response = client.get("/tickets", params={"colour": "blue"}, headers=auth_headers(agent))
    assert response.status_code == 422
