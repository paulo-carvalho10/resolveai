from fastapi.testclient import TestClient

from app.models import User
from tests.conftest import auth_headers


def create_category(client: TestClient, admin: User, **overrides: object) -> dict:
    payload = {
        "name": "Fiscal",
        "description": "Documentos fiscais",
        "subcategories": [{"name": "NF-e"}, {"name": "NFS-e"}],
        **overrides,
    }
    response = client.post("/categories", json=payload, headers=auth_headers(admin))
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_can_create_category_with_subcategories(client: TestClient, admin: User) -> None:
    category = create_category(client, admin)

    assert category["name"] == "Fiscal"
    assert [sub["name"] for sub in category["subcategories"]] == ["NF-e", "NFS-e"]


def test_category_can_route_to_default_team(client: TestClient, admin: User) -> None:
    team = client.post("/teams", json={"name": "ERP Fiscal"}, headers=auth_headers(admin)).json()
    category = create_category(client, admin, default_team_id=team["id"])

    assert category["default_team_id"] == team["id"]


def test_default_team_must_belong_to_organization(
    client: TestClient, admin: User, other_admin: User
) -> None:
    foreign_team = client.post(
        "/teams", json={"name": "Globex"}, headers=auth_headers(other_admin)
    ).json()
    response = client.post(
        "/categories",
        json={"name": "Fiscal", "default_team_id": foreign_team["id"]},
        headers=auth_headers(admin),
    )
    assert response.status_code == 404


def test_duplicate_names_are_rejected(client: TestClient, admin: User) -> None:
    category = create_category(client, admin)

    duplicate = client.post("/categories", json={"name": "fiscal"}, headers=auth_headers(admin))
    assert duplicate.json()["error"]["code"] == "CATEGORY_NAME_TAKEN"

    duplicate_sub = client.post(
        f"/categories/{category['id']}/subcategories",
        json={"name": "nf-e"},
        headers=auth_headers(admin),
    )
    assert duplicate_sub.json()["error"]["code"] == "SUBCATEGORY_NAME_TAKEN"


def test_agent_cannot_create_category(client: TestClient, agent: User) -> None:
    response = client.post("/categories", json={"name": "Fiscal"}, headers=auth_headers(agent))
    assert response.status_code == 403


def test_requester_only_sees_active_entries(
    client: TestClient, admin: User, requester: User
) -> None:
    fiscal = create_category(client, admin)
    create_category(client, admin, name="Legado", subcategories=[])
    legacy = client.get("/categories", headers=auth_headers(admin)).json()[1]

    client.patch(
        f"/categories/{legacy['id']}", json={"is_active": False}, headers=auth_headers(admin)
    )
    nfse = fiscal["subcategories"][1]
    client.patch(
        f"/subcategories/{nfse['id']}", json={"is_active": False}, headers=auth_headers(admin)
    )

    visible = client.get(
        "/categories", params={"include_inactive": True}, headers=auth_headers(requester)
    ).json()
    assert [c["name"] for c in visible] == ["Fiscal"]
    assert [s["name"] for s in visible[0]["subcategories"]] == ["NF-e"]

    everything = client.get(
        "/categories", params={"include_inactive": True}, headers=auth_headers(admin)
    ).json()
    assert [c["name"] for c in everything] == ["Fiscal", "Legado"]
    assert len(everything[0]["subcategories"]) == 2


def test_admin_can_manage_subcategories(client: TestClient, admin: User) -> None:
    category = create_category(client, admin, subcategories=[])

    created = client.post(
        f"/categories/{category['id']}/subcategories",
        json={"name": "SPED"},
        headers=auth_headers(admin),
    )
    assert created.status_code == 201
    sub_id = created.json()["id"]

    renamed = client.patch(
        f"/subcategories/{sub_id}", json={"name": "SPED Fiscal"}, headers=auth_headers(admin)
    )
    assert renamed.json()["name"] == "SPED Fiscal"

    assert client.delete(f"/subcategories/{sub_id}", headers=auth_headers(admin)).status_code == 204
    detail = client.get(f"/categories/{category['id']}", headers=auth_headers(admin)).json()
    assert detail["subcategories"] == []


def test_admin_can_delete_category(client: TestClient, admin: User) -> None:
    category = create_category(client, admin)

    assert (
        client.delete(f"/categories/{category['id']}", headers=auth_headers(admin)).status_code
        == 204
    )
    response = client.get(f"/categories/{category['id']}", headers=auth_headers(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CATEGORY_NOT_FOUND"
