from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    AnalysisStatus,
    Category,
    Organization,
    Team,
    Ticket,
    TicketAIAnalysis,
    TicketEventType,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    TicketSuggestion,
    TicketSuggestionSource,
    User,
)
from app.models.base import utcnow
from tests.conftest import auth_headers


@pytest.fixture
def scenario(
    db: Session, org: Organization, requester: User, agent: User, other_admin: User
) -> dict[str, Any]:
    """Five tickets with known timings, plus one from another organization."""
    now = utcnow()
    fiscal_team = Team(organization_id=org.id, name="ERP Fiscal")
    fiscal = Category(organization_id=org.id, name="Fiscal", default_team=fiscal_team)
    infra = Category(organization_id=org.id, name="Infraestrutura")
    db.add_all([fiscal_team, fiscal, infra])
    db.flush()

    def ticket(**values: Any) -> Ticket:
        item = Ticket(
            organization_id=org.id,
            title="Chamado de teste",
            description="Descrição do chamado de teste.",
            requester_id=requester.id,
            **values,
        )
        db.add(item)
        db.flush()
        return item

    # Resolved in 2h, within its 4h SLA; first assignment after 30 min; AI agreed on everything.
    resolved_ok = ticket(
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.HIGH,
        category=fiscal,
        team=fiscal_team,
        created_at=now - timedelta(days=2),
        resolved_at=now - timedelta(days=2) + timedelta(hours=2),
        ai_category=fiscal,
        ai_priority=TicketPriority.HIGH,
    )
    db.add(
        TicketHistory(
            ticket=resolved_ok,
            actor_id=agent.id,
            event_type=TicketEventType.ASSIGNEE_CHANGED,
            created_at=resolved_ok.created_at + timedelta(minutes=30),
        )
    )
    # Resolved in 3h, breaching its 1h SLA; AI got the category wrong.
    resolved_late = ticket(
        status=TicketStatus.CLOSED,
        priority=TicketPriority.CRITICAL,
        category=infra,
        created_at=now - timedelta(days=3),
        resolved_at=now - timedelta(days=3) + timedelta(hours=3),
        ai_category=fiscal,
        ai_priority=TicketPriority.HIGH,
    )
    # Open critical ticket past its deadline.
    ticket(
        status=TicketStatus.OPEN,
        priority=TicketPriority.CRITICAL,
        category=infra,
        created_at=now - timedelta(hours=2),
    )
    # In progress, 7h into an 8h SLA: at risk.
    ticket(
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.MEDIUM,
        created_at=now - timedelta(hours=7),
    )
    # Created before the 30-day window: counts in the queue, not in period metrics.
    ticket(
        status=TicketStatus.WAITING_USER,
        priority=TicketPriority.LOW,
        created_at=now - timedelta(days=40),
    )

    other = Organization(name="Globex Metrics")
    db.add(other)
    db.flush()
    db.add(
        Ticket(
            organization_id=other_admin.organization_id,
            title="Outra empresa",
            description="Não deve aparecer no dashboard.",
            requester_id=other_admin.id,
            status=TicketStatus.OPEN,
            priority=TicketPriority.CRITICAL,
            created_at=now,
        )
    )

    db.add_all(
        [
            TicketAIAnalysis(
                ticket=resolved_ok,
                status=AnalysisStatus.SUCCEEDED,
                provider="stub",
                model="stub",
                confidence=0.9,
                applied_fields="category,priority",
            ),
            TicketAIAnalysis(
                ticket=resolved_late,
                status=AnalysisStatus.SUCCEEDED,
                provider="stub",
                model="stub",
                confidence=0.7,
            ),
            TicketAIAnalysis(
                ticket=resolved_late, status=AnalysisStatus.FAILED, provider="stub", model="stub"
            ),
        ]
    )
    suggestion = TicketSuggestion(
        ticket=resolved_ok,
        status=AnalysisStatus.SUCCEEDED,
        provider="stub",
        model="stub",
        can_answer=True,
    )
    suggestion.sources.append(
        TicketSuggestionSource(
            article_code="KB-001", article_title="Rejeição 539", rank=1, score=0.8, cited=True
        )
    )
    db.add_all(
        [
            suggestion,
            TicketSuggestion(
                ticket=resolved_late,
                status=AnalysisStatus.SUCCEEDED,
                provider="stub",
                model="stub",
                can_answer=False,
            ),
        ]
    )
    db.commit()
    return {"fiscal": fiscal, "infra": infra}


def test_dashboard_metrics(client: TestClient, agent: User, scenario: dict[str, Any]) -> None:
    response = client.get("/analytics/dashboard", params={"days": 30}, headers=auth_headers(agent))

    assert response.status_code == 200
    data = response.json()

    assert data["indicators"] == {
        "open": 1,
        "in_progress": 1,
        "waiting_user": 1,
        "critical_open": 1,
        "sla_at_risk": 1,
        "sla_breached_open": 2,  # the critical one and the 40-day-old one
        "resolved_today": 0,
    }

    period = data["period"]
    assert (period["created"], period["resolved"]) == (4, 2)
    assert period["resolution_rate"] == 0.5
    assert period["avg_resolution_hours"] == 2.5
    assert period["avg_first_response_hours"] == 0.5
    assert (period["sla_met"], period["sla_breached"]) == (1, 1)

    assert {item["label"]: item["count"] for item in data["by_category"]} == {
        "Infraestrutura": 2,
        "Fiscal": 1,
        "Sem categoria": 1,
    }
    assert {item["label"]: item["count"] for item in data["by_priority"]} == {
        "LOW": 0,
        "MEDIUM": 1,
        "HIGH": 1,
        "CRITICAL": 2,
    }
    assert data["by_team"][0] == {"label": "Sem equipe", "count": 3}
    assert data["resolution_by_category"] == [
        {"label": "Infraestrutura", "avg_hours": 3.0, "tickets": 1},
        {"label": "Fiscal", "avg_hours": 2.0, "tickets": 1},
    ]
    assert len(data["daily"]) == 31
    assert sum(point["created"] for point in data["daily"]) == 4
    assert sum(point["resolved"] for point in data["daily"]) == 2

    ai = data["ai"]
    assert (ai["analyses"], ai["failed_analyses"], ai["auto_applied"]) == (3, 1, 1)
    assert ai["category_acceptance"] == 0.5
    assert ai["priority_acceptance"] == 0.5
    assert ai["avg_confidence"] == 0.8
    assert (ai["suggestions"], ai["suggestions_answered"]) == (2, 1)
    assert ai["estimated_minutes_saved"] == 8.0  # 1 triage x 3 min + 1 answer x 5 min
    assert ai["top_articles"] == [
        {"article_id": None, "code": "KB-001", "title": "Rejeição 539", "citations": 1}
    ]


def test_empty_organization_dashboard(client: TestClient, admin: User) -> None:
    data = client.get("/analytics/dashboard", headers=auth_headers(admin)).json()

    assert data["period"]["created"] == 0
    assert data["period"]["resolution_rate"] is None
    assert data["period"]["avg_resolution_hours"] is None
    assert data["ai"]["category_acceptance"] is None
    assert data["ai"]["top_articles"] == []


def test_requesters_cannot_see_the_dashboard(client: TestClient, requester: User) -> None:
    assert client.get("/analytics/dashboard", headers=auth_headers(requester)).status_code == 403


def test_period_is_validated(client: TestClient, agent: User) -> None:
    response = client.get("/analytics/dashboard", params={"days": 0}, headers=auth_headers(agent))
    assert response.status_code == 422
