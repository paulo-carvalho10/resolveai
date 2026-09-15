from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.scripts.seed import PASSWORD, seed


def test_seed_creates_usable_demo_data_once(client: TestClient, db: Session) -> None:
    assert seed(db) is True
    assert seed(db) is False

    login = client.post("/auth/login", json={"email": "agent@resolveai.dev", "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    tickets = client.get("/tickets", params={"sort": "-priority"}, headers=headers).json()

    assert tickets["total"] == 4
    assert tickets["items"][0]["priority"] == "CRITICAL"
    assert all(ticket["team"] is not None for ticket in tickets["items"])
