from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    KnowledgeArticle,
    KnowledgeChunk,
    Ticket,
    TicketAIAnalysis,
    TicketStatus,
    TicketSuggestion,
    User,
)
from app.scripts.demo_data import generate
from app.scripts.seed import seed
from app.services import ticket_service
from app.services.embeddings import HashingEmbedder


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_demo_data_is_deterministic_and_usable(db: Session) -> None:
    seed(db, HashingEmbedder())
    articles_before = count(db, KnowledgeArticle)

    message = generate(db, users=12, articles=6, tickets=40)

    assert "40 tickets" in message
    assert count(db, Ticket) > 40  # seed tickets plus the demo ones
    assert count(db, User) == 3 + 12
    assert count(db, KnowledgeArticle) == articles_before + 6
    assert count(db, KnowledgeChunk) > 0  # demo articles are indexed too
    assert count(db, TicketAIAnalysis) == 40
    assert 0 < count(db, TicketSuggestion) <= 40

    tickets = list(db.scalars(select(Ticket).where(Ticket.ai_confidence.is_not(None))))
    assert len(tickets) == 40
    assert all(t.category is not None and t.team is not None for t in tickets)
    assert any(t.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED) for t in tickets)
    assert any(t.status == TicketStatus.OPEN for t in tickets)
    assert all(t.resolved_at is None or t.resolved_at > t.created_at for t in tickets)
    # Closing follows the API's rule, so the auto-close job finds nothing left to do.
    assert any(t.status == TicketStatus.CLOSED for t in tickets)
    assert ticket_service.close_stale_resolved_tickets(db) == 0
    # The generator matches the AI suggestion to the real category most of the time.
    agreed = sum(t.category_id == t.ai_category_id for t in tickets)
    assert 0.7 <= agreed / len(tickets) <= 1.0


def test_demo_data_refuses_to_run_twice(db: Session) -> None:
    seed(db, HashingEmbedder())
    generate(db, users=5, articles=2, tickets=120)

    assert "already present" in generate(db, users=5, articles=2, tickets=10)
    assert count(db, Ticket) == 124  # 4 from the seed, nothing added

    generate(db, users=1, articles=1, tickets=5, force=True)
    assert count(db, Ticket) == 129
