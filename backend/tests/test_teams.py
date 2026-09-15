from fastapi.testclient import TestClient

from app.models import User
from tests.conftest import auth_headers


def create_team(client: TestClient, admin: User, name: str = "ERP Fiscal") -> dict:
    response = client.post(
        "/teams", json={"name": name, "description": "NF-e, NFS-e"}, headers=auth_headers(admin)
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_can_create_team(client: TestClient, admin: User) -> None:
    team = create_team(client, admin)

    assert team["name"] == "ERP Fiscal"
    assert team["members"] == []


def test_team_names_are_unique_per_organization(
    client: TestClient, admin: User, other_admin: User
) -> None:
    create_team(client, admin, "Infra")

    duplicate = client.post("/teams", json={"name": "infra"}, headers=auth_headers(admin))
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "TEAM_NAME_TAKEN"

    # Another organization may use the same name.
    other = client.post("/teams", json={"name": "Infra"}, headers=auth_headers(other_admin))
    assert other.status_code == 201


def test_agent_cannot_create_team(client: TestClient, agent: User) -> None:
    response = client.post("/teams", json={"name": "Infra"}, headers=auth_headers(agent))
    assert response.status_code == 403


def test_user_cannot_list_teams(client: TestClient, requester: User) -> None:
    assert client.get("/teams", headers=auth_headers(requester)).status_code == 403


def test_teams_are_isolated_between_organizations(
    client: TestClient, admin: User, agent: User, other_admin: User
) -> None:
    team = create_team(client, admin)
    create_team(client, other_admin, "Globex Team")

    listed = client.get("/teams", headers=auth_headers(agent)).json()
    assert [t["name"] for t in listed] == ["ERP Fiscal"]

    response = client.get(f"/teams/{team['id']}", headers=auth_headers(other_admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TEAM_NOT_FOUND"


def test_admin_can_add_and_remove_members(client: TestClient, admin: User, agent: User) -> None:
    team = create_team(client, admin)

    added = client.post(
        f"/teams/{team['id']}/members", json={"user_id": agent.id}, headers=auth_headers(admin)
    )
    assert added.status_code == 200
    assert [member["id"] for member in added.json()["members"]] == [agent.id]

    removed = client.delete(f"/teams/{team['id']}/members/{agent.id}", headers=auth_headers(admin))
    assert removed.status_code == 200
    assert removed.json()["members"] == []


def test_requester_cannot_join_team(client: TestClient, admin: User, requester: User) -> None:
    team = create_team(client, admin)
    response = client.post(
        f"/teams/{team['id']}/members", json={"user_id": requester.id}, headers=auth_headers(admin)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TEAM_MEMBER"


def test_cannot_add_member_from_other_organization(
    client: TestClient, admin: User, other_admin: User
) -> None:
    team = create_team(client, admin)
    response = client.post(
        f"/teams/{team['id']}/members",
        json={"user_id": other_admin.id},
        headers=auth_headers(admin),
    )
    assert response.status_code == 404


def test_admin_can_update_and_delete_team(client: TestClient, admin: User) -> None:
    team = create_team(client, admin)

    updated = client.patch(
        f"/teams/{team['id']}", json={"name": "Fiscal"}, headers=auth_headers(admin)
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Fiscal"
    assert updated.json()["description"] == "NF-e, NFS-e"

    assert client.delete(f"/teams/{team['id']}", headers=auth_headers(admin)).status_code == 204
    assert client.get(f"/teams/{team['id']}", headers=auth_headers(admin)).status_code == 404
