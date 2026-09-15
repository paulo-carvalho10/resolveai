from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import PriorityRule
from app.scripts.seed import PASSWORD, PRIORITY_RULES, seed


def test_seed_creates_usable_demo_data_once(client: TestClient, db: Session) -> None:
    assert seed(db) is True
    assert seed(db) is False

    login = client.post("/auth/login", json={"email": "agent@resolveai.dev", "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    tickets = client.get("/tickets", params={"sort": "-priority"}, headers=headers).json()

    assert tickets["total"] == 4
    assert tickets["items"][0]["priority"] == "CRITICAL"
    assert all(ticket["team"] is not None for ticket in tickets["items"])

    rules = client.get("/priority-rules", headers=headers).json()
    assert len(rules) == len(PRIORITY_RULES)


def test_seed_adds_rules_to_databases_seeded_before_stage_2(db: Session) -> None:
    seed(db)
    db.execute(delete(PriorityRule))
    db.commit()

    assert seed(db) is True
    assert db.scalar(select(func.count()).select_from(PriorityRule)) == len(PRIORITY_RULES)
