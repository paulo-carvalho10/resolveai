"""RAG suggestions for tickets: retrieve relevant articles, generate a grounded answer, cite it.

ticket -> embed(query) -> vector search (pgvector) -> top articles
       -> answer generator (Claude or extractive) -> suggestion + cited sources
"""

import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logger import log_event
from app.models import (
    AnalysisStatus,
    Ticket,
    TicketStatus,
    TicketSuggestion,
    TicketSuggestionSource,
    User,
)
from app.services import knowledge_service
from app.services.ai_classifier import TicketText
from app.services.answer_generator import AnswerGenerator, SourceArticle
from app.services.claude import AIError
from app.services.embeddings import Embedder, EmbeddingError

logger = logging.getLogger(__name__)


def suggest_solution(
    db: Session,
    ticket: Ticket,
    embedder: Embedder,
    generator: AnswerGenerator,
    requested_by: User | None = None,
) -> TicketSuggestion:
    """Store a suggestion for the ticket. Provider failures are stored as FAILED, not raised."""
    settings = get_settings()
    suggestion = TicketSuggestion(
        ticket=ticket,
        requested_by=requested_by,
        provider=generator.provider,
        model=generator.model,
        embedding_model=embedder.model,
    )

    try:
        retrieved = knowledge_service.search(
            db,
            ticket.organization_id,
            f"{ticket.title}\n\n{ticket.description}",
            embedder,
            limit=settings.rag_top_k,
            min_score=settings.effective_rag_min_score,
        )
        articles = [
            SourceArticle(
                code=item.article.code,
                title=item.article.title,
                passages=tuple(scored.chunk.content for scored in item.chunks),
            )
            for item in retrieved
        ]
        result = generator.generate(TicketText(ticket.title, ticket.description), articles)
    except (EmbeddingError, AIError) as exc:
        suggestion.status = AnalysisStatus.FAILED
        suggestion.error_code = exc.code
        db.add(suggestion)
        db.commit()
        log_event(
            logger,
            "ai.suggestion.failed",
            level=logging.ERROR,
            ticket_id=ticket.id,
            error=exc.code,
        )
        return suggestion

    # Only articles that were actually retrieved can be cited; anything else is discarded.
    retrieved_codes = {item.article.code for item in retrieved}
    cited = {code for code in result.answer.sources if code in retrieved_codes}
    can_answer = result.answer.can_answer and bool(retrieved)

    suggestion.status = AnalysisStatus.SUCCEEDED
    suggestion.model = result.model
    suggestion.can_answer = can_answer
    suggestion.answer = result.answer.answer
    suggestion.input_tokens = result.input_tokens
    suggestion.output_tokens = result.output_tokens
    suggestion.latency_ms = result.latency_ms
    for rank, item in enumerate(retrieved, start=1):
        suggestion.sources.append(
            TicketSuggestionSource(
                article_id=item.article.id,
                article_code=item.article.code,
                article_title=item.article.title,
                rank=rank,
                score=round(item.score, 4),
                cited=can_answer and item.article.code in cited,
            )
        )
    db.add(suggestion)
    db.commit()
    log_event(
        logger,
        "ai.suggestion.created",
        ticket_id=ticket.id,
        provider=result.provider,
        can_answer=can_answer,
        retrieved=len(retrieved),
        cited=",".join(sorted(cited)) or "-",
    )
    return suggestion


def suggest_on_request(
    db: Session, ticket: Ticket, embedder: Embedder, generator: AnswerGenerator, actor: User
) -> TicketSuggestion:
    if ticket.status == TicketStatus.CLOSED:
        raise AppError("TICKET_CLOSED", "Closed tickets cannot be changed.", 409)
    suggestion = suggest_solution(db, ticket, embedder, generator, requested_by=actor)
    if suggestion.status == AnalysisStatus.FAILED:
        raise AppError(
            suggestion.error_code or "AI_PROVIDER_ERROR",
            "Could not generate a suggestion right now; try again later.",
            502,
        )
    return get_suggestion(db, suggestion.id)


def suggest_in_background(
    session_factory: Callable[[], Session],
    embedder: Embedder,
    generator: AnswerGenerator,
    ticket_id: int,
) -> None:
    try:
        with session_factory() as db:
            ticket = db.get(Ticket, ticket_id)
            if ticket is None or ticket.status == TicketStatus.CLOSED:
                return
            suggest_solution(db, ticket, embedder, generator)
    except Exception as exc:
        log_event(
            logger,
            "ai.suggestion.crashed",
            level=logging.ERROR,
            exc_info=exc,
            ticket_id=ticket_id,
        )


_SUGGESTION_RELATIONS = (
    selectinload(TicketSuggestion.sources),
    selectinload(TicketSuggestion.requested_by),
)


def get_suggestion(db: Session, suggestion_id: int) -> TicketSuggestion:
    suggestion = db.scalar(
        select(TicketSuggestion)
        .where(TicketSuggestion.id == suggestion_id)
        .options(*_SUGGESTION_RELATIONS)
        .execution_options(populate_existing=True)
    )
    assert suggestion is not None
    return suggestion


def list_suggestions(db: Session, ticket: Ticket) -> list[TicketSuggestion]:
    stmt = (
        select(TicketSuggestion)
        .where(TicketSuggestion.ticket_id == ticket.id)
        .options(*_SUGGESTION_RELATIONS)
        .order_by(TicketSuggestion.id.desc())
    )
    return list(db.scalars(stmt))
