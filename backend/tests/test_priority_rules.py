import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Organization, PriorityRule, TicketPriority, User
from app.services.priority_service import highest, match_rule
from tests.conftest import auth_headers

OUTAGE_RULE = {
    "name": "Sistema fora do ar",
    "keywords": ["sistema fora do ar", "ninguém consegue acessar"],
    "priority": "CRITICAL",
}


@pytest.fixture(autouse=True)
def _no_ai_on_create(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_analyze_on_create", False)


def create_rule(client: TestClient, admin: User, **overrides: object) -> dict:
    response = client.post(
        "/priority-rules", json={**OUTAGE_RULE, **overrides}, headers=auth_headers(admin)
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- CRUD ----------------------------------------------------------------------------------


def test_admin_manages_rules(client: TestClient, admin: User, agent: User) -> None:
    rule = create_rule(client, admin, keywords=["Fora do ar", "fora do AR", " parou tudo "])
    # Duplicates differing only by case/accents are dropped; the first spelling is kept.
    assert rule["keywords"] == ["Fora do ar", "parou tudo"]

    listed = client.get("/priority-rules", headers=auth_headers(agent)).json()
    assert [r["name"] for r in listed] == ["Sistema fora do ar"]

    updated = client.patch(
        f"/priority-rules/{rule['id']}",
        json={"priority": "HIGH", "is_active": False},
        headers=auth_headers(admin),
    ).json()
    assert (updated["priority"], updated["is_active"]) == ("HIGH", False)

    assert (
        client.delete(f"/priority-rules/{rule['id']}", headers=auth_headers(admin)).status_code
        == 204
    )
    assert (
        client.get(f"/priority-rules/{rule['id']}", headers=auth_headers(admin)).status_code == 404
    )


def test_agent_cannot_create_rule_and_user_cannot_list(
    client: TestClient, agent: User, requester: User
) -> None:
    assert (
        client.post("/priority-rules", json=OUTAGE_RULE, headers=auth_headers(agent)).status_code
        == 403
    )
    assert client.get("/priority-rules", headers=auth_headers(requester)).status_code == 403


def test_rule_validation_and_duplicates(client: TestClient, admin: User) -> None:
    create_rule(client, admin)

    duplicate = client.post(
        "/priority-rules",
        json={**OUTAGE_RULE, "name": "SISTEMA FORA DO AR"},
        headers=auth_headers(admin),
    )
    assert duplicate.json()["error"]["code"] == "PRIORITY_RULE_NAME_TAKEN"

    empty = client.post(
        "/priority-rules",
        json={**OUTAGE_RULE, "name": "Vazia", "keywords": []},
        headers=auth_headers(admin),
    )
    assert empty.status_code == 422


def test_rules_are_isolated_between_organizations(
    client: TestClient, admin: User, other_admin: User
) -> None:
    rule = create_rule(client, admin)

    assert (
        client.get(f"/priority-rules/{rule['id']}", headers=auth_headers(other_admin)).status_code
        == 404
    )
    assert client.get("/priority-rules", headers=auth_headers(other_admin)).json() == []


# --- Matching ------------------------------------------------------------------------------


def _rule(
    org: Organization, name: str, keywords: list[str], priority: TicketPriority, active: bool = True
) -> PriorityRule:
    return PriorityRule(
        organization_id=org.id, name=name, keywords=keywords, priority=priority, is_active=active
    )


def test_match_rule_is_accent_case_and_word_aware(db: Session, org: Organization) -> None:
    db.add_all(
        [
            _rule(org, "Faturamento", ["não consigo emitir"], TicketPriority.HIGH),
            _rule(org, "Queda", ["fora do ar"], TicketPriority.CRITICAL),
            _rule(org, "Desligada", ["parou tudo"], TicketPriority.CRITICAL, active=False),
        ]
    )
    db.commit()

    both = match_rule(db, org.id, "NAO CONSIGO EMITIR notas e o sistema está Fora do Ar")
    assert both is not None and both.name == "Queda"  # highest priority wins

    only_high = match_rule(db, org.id, "Não consigo emitir a nota")
    assert only_high is not None and only_high.name == "Faturamento"

    assert match_rule(db, org.id, "Parou tudo aqui") is None  # inactive
    assert match_rule(db, org.id, "O fornecedor está foradoar") is None  # not a whole phrase


def test_highest_priority() -> None:
    assert highest(TicketPriority.LOW, None, TicketPriority.HIGH) == TicketPriority.HIGH
    assert highest(None, None) is None


# --- Applied on ticket creation ------------------------------------------------------------


def test_rule_raises_priority_when_ticket_is_created(
    client: TestClient, admin: User, requester: User, agent: User
) -> None:
    create_rule(client, admin)

    ticket = client.post(
        "/tickets",
        json={
            "title": "SISTEMA FORA DO AR",
            "description": "Ninguém consegue acessar o ERP desde as 8h.",
        },
        headers=auth_headers(requester),
    ).json()

    assert ticket["priority"] == "CRITICAL"
    history = client.get(f"/tickets/{ticket['id']}/history", headers=auth_headers(agent)).json()
    assert [(e["event_type"], e["new_value"], e["actor"]) for e in history] == [
        ("CREATED", None, history[0]["actor"]),
        ("RULE_APPLIED", "Sistema fora do ar", None),
        ("PRIORITY_CHANGED", "CRITICAL", None),
    ]


def test_ticket_without_matching_rule_keeps_default_priority(
    client: TestClient, admin: User, requester: User
) -> None:
    create_rule(client, admin)
    ticket = client.post(
        "/tickets",
        json={"title": "Dúvida sobre relatório", "description": "Como exporto o relatório mensal?"},
        headers=auth_headers(requester),
    ).json()
    assert ticket["priority"] == "MEDIUM"
