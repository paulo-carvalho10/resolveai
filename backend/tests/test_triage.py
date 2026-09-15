"""End-to-end triage (rules + AI + routing) through the API, with a controllable classifier."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Ticket, User
from app.services.ai_classifier import (
    Catalog,
    Classification,
    ClassificationResult,
    ClassifierError,
    TicketText,
)
from tests.conftest import auth_headers

NFE_TICKET = {
    "title": "Não consigo emitir notas",
    "description": "Precisamos fechar o faturamento hoje e o sistema recusa a transmissão.",
}


class StubClassifier:
    provider = "stub"
    model = "stub-1"

    def __init__(self) -> None:
        self.outcome: Classification | Exception = suggestion()
        self.calls: list[tuple[TicketText, Catalog]] = []

    def classify(self, ticket: TicketText, catalog: Catalog) -> ClassificationResult:
        self.calls.append((ticket, catalog))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return ClassificationResult(
            classification=self.outcome,
            provider=self.provider,
            model=self.model,
            latency_ms=42,
            input_tokens=900,
            output_tokens=120,
        )


def suggestion(**overrides: Any) -> Classification:
    values: dict[str, Any] = {
        "category": "Fiscal",
        "subcategory": "NF-e",
        "team": None,
        "priority": "HIGH",
        "urgency": "HIGH",
        "summary": "Emissão de NF-e bloqueada no fechamento.",
        "reasoning": "Processo de faturamento parado com prazo hoje.",
        "confidence": 0.92,
    }
    return Classification(**{**values, **overrides})


@pytest.fixture
def classifier() -> StubClassifier:
    return StubClassifier()


@pytest.fixture
def catalog(client: TestClient, admin: User) -> dict[str, Any]:
    """Fiscal routes to ERP Fiscal by default; Infraestrutura has no default team."""
    headers = auth_headers(admin)
    fiscal_team = client.post("/teams", json={"name": "ERP Fiscal"}, headers=headers).json()
    infra_team = client.post("/teams", json={"name": "Infraestrutura TI"}, headers=headers).json()
    fiscal = client.post(
        "/categories",
        json={
            "name": "Fiscal",
            "default_team_id": fiscal_team["id"],
            "subcategories": [{"name": "NF-e"}, {"name": "NFS-e"}],
        },
        headers=headers,
    ).json()
    infra = client.post(
        "/categories",
        json={"name": "Infraestrutura", "subcategories": [{"name": "VPN"}]},
        headers=headers,
    ).json()
    return {"fiscal": fiscal, "infra": infra, "fiscal_team": fiscal_team, "infra_team": infra_team}


@pytest.fixture
def open_ticket(client: TestClient, requester: User) -> Callable[..., dict[str, Any]]:
    def factory(**overrides: Any) -> dict[str, Any]:
        response = client.post(
            "/tickets", json={**NFE_TICKET, **overrides}, headers=auth_headers(requester)
        )
        assert response.status_code == 201, response.text
        return response.json()

    return factory


def fetch(client: TestClient, user: User, ticket_id: int) -> dict[str, Any]:
    return client.get(f"/tickets/{ticket_id}", headers=auth_headers(user)).json()


def history(client: TestClient, user: User, ticket_id: int) -> list[dict[str, Any]]:
    return client.get(f"/tickets/{ticket_id}/history", headers=auth_headers(user)).json()


def analyses(client: TestClient, user: User, ticket_id: int) -> list[dict[str, Any]]:
    return client.get(f"/tickets/{ticket_id}/ai/analyses", headers=auth_headers(user)).json()


# --- Automatic analysis on creation --------------------------------------------------------


def test_confident_ai_classifies_prioritizes_and_routes(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
) -> None:
    created = open_ticket()
    # The response is sent before the background analysis runs.
    assert created["category"] is None
    assert created["ai_analyzed_at"] is None

    ticket = fetch(client, agent, created["id"])
    assert ticket["category"]["name"] == "Fiscal"
    assert ticket["subcategory"]["name"] == "NF-e"
    assert ticket["priority"] == "HIGH"
    assert ticket["team"]["name"] == "ERP Fiscal"  # category default team
    assert ticket["ai_category"]["name"] == "Fiscal"
    assert ticket["ai_priority"] == "HIGH"
    assert ticket["ai_confidence"] == 0.92
    assert ticket["ai_summary"] == "Emissão de NF-e bloqueada no fechamento."

    events = [
        (e["event_type"], e["new_value"], e["actor"])
        for e in history(client, agent, ticket["id"])[1:]
    ]
    assert events == [
        ("AI_ANALYZED", "Fiscal / NF-e · HIGH · 92%", None),
        ("CATEGORY_CHANGED", "Fiscal", None),
        ("SUBCATEGORY_CHANGED", "NF-e", None),
        ("PRIORITY_CHANGED", "HIGH", None),
        ("TEAM_CHANGED", "ERP Fiscal", None),
    ]

    [analysis] = analyses(client, agent, ticket["id"])
    assert analysis["status"] == "SUCCEEDED"
    assert analysis["applied_fields"] == ["category", "subcategory", "priority", "team"]
    assert (analysis["provider"], analysis["model"]) == ("stub", "stub-1")
    assert (analysis["input_tokens"], analysis["output_tokens"], analysis["latency_ms"]) == (
        900,
        120,
        42,
    )
    assert analysis["requested_by"] is None

    # The classifier received the organization's catalog.
    _, sent_catalog = classifier.calls[0]
    assert {c.name for c in sent_catalog.categories} == {"Fiscal", "Infraestrutura"}
    assert {t.name for t in sent_catalog.teams} == {"ERP Fiscal", "Infraestrutura TI"}


def test_low_confidence_is_stored_but_not_applied(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
) -> None:
    classifier.outcome = suggestion(confidence=0.4, priority="CRITICAL")

    ticket = fetch(client, agent, open_ticket()["id"])

    assert ticket["category"] is None
    assert ticket["priority"] == "MEDIUM"
    assert ticket["team"] is None
    assert ticket["ai_category"]["name"] == "Fiscal"
    assert ticket["ai_priority"] == "CRITICAL"
    assert ticket["ai_confidence"] == 0.4
    assert analyses(client, agent, ticket["id"])[0]["applied_fields"] == []


def test_ai_uses_suggested_team_when_category_has_no_default(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
) -> None:
    classifier.outcome = suggestion(
        category="infraestrutura", subcategory="vpn", team="INFRAESTRUTURA TI", priority="MEDIUM"
    )

    ticket = fetch(client, agent, open_ticket()["id"])

    # Names are matched case-insensitively against the catalog.
    assert ticket["category"]["name"] == "Infraestrutura"
    assert ticket["subcategory"]["name"] == "VPN"
    assert ticket["team"]["name"] == "Infraestrutura TI"


def test_unknown_names_from_ai_are_ignored(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
) -> None:
    classifier.outcome = suggestion(
        category="Contabilidade", subcategory="Balanço", team="Financeiro"
    )

    ticket = fetch(client, agent, open_ticket()["id"])

    assert ticket["category"] is None
    assert ticket["ai_category"] is None
    assert ticket["ai_team"] is None
    [analysis] = analyses(client, agent, ticket["id"])
    assert analysis["category_name"] == "Contabilidade"  # raw answer kept for auditing
    assert analysis["applied_fields"] == ["priority"]


def test_category_chosen_by_requester_is_kept_and_routed_immediately(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
) -> None:
    classifier.outcome = suggestion(category="Infraestrutura", subcategory="VPN")

    created = open_ticket(category_id=catalog["fiscal"]["id"])
    # Routing by the chosen category happens synchronously, before any AI.
    assert created["team"]["name"] == "ERP Fiscal"

    ticket = fetch(client, agent, created["id"])
    assert ticket["category"]["name"] == "Fiscal"
    assert ticket["subcategory"] is None  # AI subcategory belongs to another category
    assert ticket["ai_category"]["name"] == "Infraestrutura"


# --- Rules + AI ----------------------------------------------------------------------------


def create_rule(client: TestClient, admin: User, keywords: list[str], priority: str) -> None:
    response = client.post(
        "/priority-rules",
        json={"name": f"Regra {priority}", "keywords": keywords, "priority": priority},
        headers=auth_headers(admin),
    )
    assert response.status_code == 201


def test_rule_is_a_floor_the_ai_cannot_lower(
    client: TestClient,
    admin: User,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
) -> None:
    create_rule(client, admin, ["fechar o faturamento"], "CRITICAL")
    classifier.outcome = suggestion(priority="LOW")

    created = open_ticket()
    assert created["priority"] == "CRITICAL"  # rule applied before the response

    ticket = fetch(client, agent, created["id"])
    assert ticket["priority"] == "CRITICAL"
    assert ticket["ai_priority"] == "LOW"
    [analysis] = analyses(client, agent, ticket["id"])
    assert analysis["matched_rule"]["name"] == "Regra CRITICAL"
    assert "priority" not in analysis["applied_fields"]


def test_ai_can_raise_priority_above_the_rule(
    client: TestClient,
    admin: User,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
) -> None:
    create_rule(client, admin, ["faturamento"], "HIGH")
    classifier.outcome = suggestion(priority="CRITICAL")

    ticket = fetch(client, agent, open_ticket()["id"])

    assert ticket["priority"] == "CRITICAL"


# --- Failures ------------------------------------------------------------------------------


def test_ai_failure_does_not_block_ticket_creation(
    client: TestClient,
    admin: User,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
) -> None:
    create_rule(client, admin, ["faturamento"], "HIGH")
    classifier.outcome = ClassifierError("AI_TIMEOUT", "timeout")

    ticket = fetch(client, agent, open_ticket()["id"])

    assert ticket["priority"] == "HIGH"  # rules still work without AI
    assert ticket["ai_analyzed_at"] is None
    assert history(client, agent, ticket["id"])[-1]["event_type"] == "AI_ANALYSIS_FAILED"
    [analysis] = analyses(client, agent, ticket["id"])
    assert (analysis["status"], analysis["error_code"]) == ("FAILED", "AI_TIMEOUT")


def test_unexpected_crash_in_background_is_contained(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
) -> None:
    classifier.outcome = RuntimeError("bug")

    created = open_ticket()

    assert fetch(client, agent, created["id"])["ai_analyzed_at"] is None


def test_analysis_can_be_disabled_on_create(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "ai_analyze_on_create", False)

    ticket = open_ticket()

    assert classifier.calls == []
    assert analyses(client, agent, ticket["id"]) == []


# --- Manual analysis -----------------------------------------------------------------------


def test_manual_analysis_never_overrides_human_edits(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "ai_analyze_on_create", False)
    ticket = open_ticket()
    client.patch(
        f"/tickets/{ticket['id']}",
        json={"priority": "LOW", "team_id": catalog["infra_team"]["id"]},
        headers=auth_headers(agent),
    )
    classifier.outcome = suggestion(priority="CRITICAL")

    response = client.post(f"/tickets/{ticket['id']}/ai/analyze", headers=auth_headers(agent))

    assert response.status_code == 200
    assert response.json()["applied_fields"] == ["category", "subcategory"]
    assert response.json()["requested_by"]["id"] == agent.id
    updated = fetch(client, agent, ticket["id"])
    assert updated["priority"] == "LOW"
    assert updated["team"]["name"] == "Infraestrutura TI"
    assert updated["category"]["name"] == "Fiscal"


def test_manual_analysis_failure_returns_502_and_is_recorded(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "ai_analyze_on_create", False)
    ticket = open_ticket()
    classifier.outcome = ClassifierError("AI_RATE_LIMITED", "slow down")

    response = client.post(f"/tickets/{ticket['id']}/ai/analyze", headers=auth_headers(agent))

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RATE_LIMITED"
    assert analyses(client, agent, ticket["id"])[0]["status"] == "FAILED"


def test_manual_analysis_permissions_and_closed_tickets(
    client: TestClient,
    agent: User,
    requester: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
) -> None:
    ticket = open_ticket()
    url = f"/tickets/{ticket['id']}/ai/analyze"

    assert client.post(url, headers=auth_headers(requester)).status_code == 403
    assert (
        client.get(
            f"/tickets/{ticket['id']}/ai/analyses", headers=auth_headers(requester)
        ).status_code
        == 403
    )

    client.patch(f"/tickets/{ticket['id']}", json={"status": "CLOSED"}, headers=auth_headers(agent))
    response = client.post(url, headers=auth_headers(agent))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TICKET_CLOSED"


def test_analyses_are_listed_newest_first(
    client: TestClient,
    agent: User,
    catalog: dict[str, Any],
    open_ticket: Callable[..., dict[str, Any]],
    classifier: StubClassifier,
    db: Session,
) -> None:
    ticket = open_ticket()
    classifier.outcome = suggestion(confidence=0.99, summary="Segunda análise.")
    client.post(f"/tickets/{ticket['id']}/ai/analyze", headers=auth_headers(agent))

    summaries = [a["summary"] for a in analyses(client, agent, ticket["id"])]
    assert summaries == ["Segunda análise.", "Emissão de NF-e bloqueada no fechamento."]
    stored = db.get(Ticket, ticket["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.ai_summary == "Segunda análise."
