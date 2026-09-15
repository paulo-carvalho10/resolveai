from fastapi.testclient import TestClient

from app.models import User
from tests.conftest import PASSWORD, auth_headers


def test_admin_can_create_user(client: TestClient, admin: User) -> None:
    payload = {
        "email": "New.Agent@acme.com",
        "full_name": "New Agent",
        "password": "agent-password",
        "role": "AGENT",
    }
    response = client.post("/users", json=payload, headers=auth_headers(admin))

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.agent@acme.com"
    assert body["role"] == "AGENT"
    assert body["organization_id"] == admin.organization_id

    login = client.post(
        "/auth/login", json={"email": "new.agent@acme.com", "password": "agent-password"}
    )
    assert login.status_code == 200


def test_agent_cannot_create_user(client: TestClient, agent: User) -> None:
    payload = {"email": "x@acme.com", "full_name": "X User", "password": "password123"}
    response = client.post("/users", json=payload, headers=auth_headers(agent))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_user_cannot_list_users(client: TestClient, requester: User) -> None:
    assert client.get("/users", headers=auth_headers(requester)).status_code == 403


def test_agent_can_list_users_of_own_organization_only(
    client: TestClient, admin: User, agent: User, requester: User, other_admin: User
) -> None:
    response = client.get("/users", headers=auth_headers(agent))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert {user["id"] for user in body["items"]} == {admin.id, agent.id, requester.id}


def test_list_users_filters_by_role_and_search(
    client: TestClient, admin: User, agent: User, requester: User
) -> None:
    by_role = client.get("/users", params={"role": "AGENT"}, headers=auth_headers(admin)).json()
    assert [user["id"] for user in by_role["items"]] == [agent.id]

    by_name = client.get("/users", params={"q": "joao"}, headers=auth_headers(admin)).json()
    assert [user["id"] for user in by_name["items"]] == [requester.id]


def test_admin_cannot_see_user_from_other_organization(
    client: TestClient, admin: User, other_admin: User
) -> None:
    response = client.get(f"/users/{other_admin.id}", headers=auth_headers(admin))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


def test_admin_can_change_role_and_deactivate(
    client: TestClient, admin: User, requester: User
) -> None:
    response = client.patch(
        f"/users/{requester.id}",
        json={"role": "AGENT", "is_active": False},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "AGENT"
    assert response.json()["is_active"] is False

    login = client.post("/auth/login", json={"email": requester.email, "password": PASSWORD})
    assert login.status_code == 403


def test_agent_cannot_deactivate_user(client: TestClient, agent: User, requester: User) -> None:
    response = client.patch(
        f"/users/{requester.id}", json={"is_active": False}, headers=auth_headers(agent)
    )
    assert response.status_code == 403


def test_admin_cannot_demote_or_deactivate_self(client: TestClient, admin: User) -> None:
    for payload in ({"role": "USER"}, {"is_active": False}):
        response = client.patch(f"/users/{admin.id}", json=payload, headers=auth_headers(admin))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CANNOT_MODIFY_SELF"


def test_admin_can_rename_self(client: TestClient, admin: User) -> None:
    response = client.patch(
        f"/users/{admin.id}", json={"full_name": "Ana Souza"}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Ana Souza"
