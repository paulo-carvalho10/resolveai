"""Automatic triage: business rules first, then AI, combined into one result.

    ticket created -> priority rules + category routing (synchronous, deterministic)
                   -> AI classification (background) -> combine -> apply what is safe to apply

What "safe" means:
- The AI suggestion is always stored on the ticket (`ai_*` fields) and in `ticket_ai_analyses`.
- It is only applied when confidence >= AI_AUTO_APPLY_MIN_CONFIDENCE.
- It only fills empty fields, and never touches a field a person has already edited.
- A matching priority rule is a floor: the AI can raise the priority above it, never below.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logger import log_event
from app.core.text import normalize
from app.models import (
    AnalysisStatus,
    Category,
    PriorityRule,
    Subcategory,
    Team,
    Ticket,
    TicketAIAnalysis,
    TicketEventType,
    TicketPriority,
    TicketStatus,
    User,
)
from app.models.base import utcnow
from app.services import priority_service, routing_service
from app.services.ai_classifier import (
    Catalog,
    CatalogCategory,
    CatalogTeam,
    Classifier,
    TicketText,
)
from app.services.claude import AIError
from app.services.ticket_history import display_name, fields_changed_by_humans, record_event

logger = logging.getLogger(__name__)


# --- On creation ---------------------------------------------------------------------------


def apply_creation_rules(db: Session, ticket: Ticket) -> None:
    """Run before the first commit, so the ticket is already prioritized and routed when saved."""
    ticket.priority = ticket.priority or TicketPriority.MEDIUM
    rule = priority_service.match_rule(db, ticket.organization_id, _ticket_text(ticket))
    if rule is not None:
        _raise_priority_by_rule(db, ticket, rule)

    team = routing_service.resolve_team(ticket.category, suggested_team=None)
    if team is not None and ticket.team is None:
        record_event(db, ticket, None, TicketEventType.TEAM_CHANGED, "team", None, team.name)
        ticket.team = team


# --- AI analysis ---------------------------------------------------------------------------


@dataclass
class _CatalogIndex:
    """Maps names returned by the classifier back to rows of this organization."""

    categories: dict[str, Category] = field(default_factory=dict)
    subcategories: dict[tuple[int, str], Subcategory] = field(default_factory=dict)
    teams: dict[str, Team] = field(default_factory=dict)

    def category(self, name: str | None) -> Category | None:
        return self.categories.get(normalize(name)) if name else None

    def subcategory(self, category: Category | None, name: str | None) -> Subcategory | None:
        if category is None or not name:
            return None
        return self.subcategories.get((category.id, normalize(name)))

    def team(self, name: str | None) -> Team | None:
        return self.teams.get(normalize(name)) if name else None


def analyze_ticket(
    db: Session,
    ticket: Ticket,
    classifier: Classifier,
    requested_by: User | None = None,
) -> TicketAIAnalysis:
    """Classify, store the suggestion, apply what is safe and commit. Never raises on AI errors."""
    catalog, index = _load_catalog(db, ticket.organization_id)
    text = TicketText(title=ticket.title, description=ticket.description)

    try:
        result = classifier.classify(text, catalog)
    except AIError as exc:
        analysis = TicketAIAnalysis(
            ticket=ticket,
            requested_by=requested_by,
            status=AnalysisStatus.FAILED,
            provider=classifier.provider,
            model=classifier.model,
            error_code=exc.code,
        )
        db.add(analysis)
        record_event(db, ticket, None, TicketEventType.AI_ANALYSIS_FAILED, new_value=exc.code)
        db.commit()
        log_event(
            logger,
            "ai.classification.failed",
            level=logging.ERROR,
            ticket_id=ticket.id,
            provider=classifier.provider,
            error=exc.code,
        )
        return analysis

    suggestion = result.classification
    confidence = min(max(suggestion.confidence, 0.0), 1.0)
    category = index.category(suggestion.category)
    subcategory = index.subcategory(category, suggestion.subcategory)
    team = index.team(suggestion.team)
    ai_priority = TicketPriority(suggestion.priority)
    rule = priority_service.match_rule(db, ticket.organization_id, _ticket_text(ticket))

    ticket.ai_category = category
    ticket.ai_subcategory = subcategory
    ticket.ai_team = team
    ticket.ai_priority = ai_priority
    ticket.ai_confidence = confidence
    ticket.ai_summary = suggestion.summary
    ticket.ai_analyzed_at = utcnow()

    label = " / ".join(filter(None, [display_name(category), display_name(subcategory)]))
    record_event(
        db,
        ticket,
        None,
        TicketEventType.AI_ANALYZED,
        "ai",
        new_value=f"{label or 'Sem categoria'} · {ai_priority} · {round(confidence * 100)}%",
    )

    confident = confidence >= get_settings().ai_auto_apply_min_confidence
    applied = _apply_suggestion(
        db, ticket, confident, category, subcategory, team, ai_priority, rule
    )

    analysis = TicketAIAnalysis(
        ticket=ticket,
        requested_by=requested_by,
        status=AnalysisStatus.SUCCEEDED,
        provider=result.provider,
        model=result.model,
        category_name=suggestion.category,
        subcategory_name=suggestion.subcategory,
        team_name=suggestion.team,
        priority=ai_priority,
        urgency=TicketPriority(suggestion.urgency),
        summary=suggestion.summary,
        reasoning=suggestion.reasoning,
        confidence=confidence,
        matched_rule=rule,
        applied_fields=",".join(applied) or None,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
    )
    db.add(analysis)
    db.commit()
    log_event(
        logger,
        "ai.classification.applied",
        ticket_id=ticket.id,
        provider=result.provider,
        confidence=confidence,
        applied=",".join(applied) or "-",
    )
    return analysis


def analyze_ticket_on_request(
    db: Session, ticket: Ticket, classifier: Classifier, actor: User
) -> TicketAIAnalysis:
    """Manual re-analysis by an agent. Unlike the background run, AI failures become errors."""
    if ticket.status == TicketStatus.CLOSED:
        raise AppError("TICKET_CLOSED", "Closed tickets cannot be changed.", 409)
    analysis = analyze_ticket(db, ticket, classifier, requested_by=actor)
    if analysis.status == AnalysisStatus.FAILED:
        raise AppError(
            analysis.error_code or "AI_PROVIDER_ERROR",
            "The AI analysis failed. The ticket was not changed; try again later.",
            502,
        )
    return analysis


def analyze_in_background(
    session_factory: Callable[[], Session], classifier: Classifier, ticket_id: int
) -> None:
    """Entry point for FastAPI background tasks: own session, never lets an exception escape."""
    try:
        with session_factory() as db:
            ticket = db.get(Ticket, ticket_id)
            if ticket is None or ticket.status == TicketStatus.CLOSED:
                return
            analyze_ticket(db, ticket, classifier)
    except Exception as exc:
        log_event(
            logger,
            "ai.classification.crashed",
            level=logging.ERROR,
            exc_info=exc,
            ticket_id=ticket_id,
        )


def list_analyses(db: Session, ticket: Ticket) -> list[TicketAIAnalysis]:
    stmt = (
        select(TicketAIAnalysis)
        .where(TicketAIAnalysis.ticket_id == ticket.id)
        .options(
            selectinload(TicketAIAnalysis.requested_by),
            selectinload(TicketAIAnalysis.matched_rule),
        )
        .order_by(TicketAIAnalysis.id.desc())
    )
    return list(db.scalars(stmt))


# --- Helpers -------------------------------------------------------------------------------


def _ticket_text(ticket: Ticket) -> str:
    return f"{ticket.title}\n{ticket.description}"


def _raise_priority_by_rule(db: Session, ticket: Ticket, rule: PriorityRule) -> bool:
    target = priority_service.highest(rule.priority, ticket.priority)
    if target == ticket.priority:
        return False
    record_event(db, ticket, None, TicketEventType.RULE_APPLIED, "priority_rule", None, rule.name)
    record_event(
        db, ticket, None, TicketEventType.PRIORITY_CHANGED, "priority", ticket.priority, target
    )
    ticket.priority = target
    return True


def _apply_suggestion(
    db: Session,
    ticket: Ticket,
    confident: bool,
    category: Category | None,
    subcategory: Subcategory | None,
    team: Team | None,
    ai_priority: TicketPriority,
    rule: PriorityRule | None,
) -> list[str]:
    locked = fields_changed_by_humans(db, ticket)
    applied: list[str] = []

    if confident and category is not None and "category" not in locked:
        if ticket.category is None:
            record_event(
                db, ticket, None, TicketEventType.CATEGORY_CHANGED, "category", None, category.name
            )
            ticket.category = category
            applied.append("category")
        if (
            ticket.category is category
            and ticket.subcategory is None
            and subcategory is not None
            and "subcategory" not in locked
        ):
            record_event(
                db,
                ticket,
                None,
                TicketEventType.SUBCATEGORY_CHANGED,
                "subcategory",
                None,
                subcategory.name,
            )
            ticket.subcategory = subcategory
            applied.append("subcategory")

    if "priority" not in locked:
        if confident:
            target = priority_service.highest(ai_priority, rule.priority if rule else None)
            if target is not None and target != ticket.priority:
                record_event(
                    db,
                    ticket,
                    None,
                    TicketEventType.PRIORITY_CHANGED,
                    "priority",
                    ticket.priority,
                    target,
                )
                ticket.priority = target
                applied.append("priority")
        elif rule is not None and _raise_priority_by_rule(db, ticket, rule):
            applied.append("priority")

    if "team" not in locked and ticket.team is None:
        routed = routing_service.resolve_team(ticket.category, team if confident else None)
        if routed is not None:
            record_event(db, ticket, None, TicketEventType.TEAM_CHANGED, "team", None, routed.name)
            ticket.team = routed
            applied.append("team")

    return applied


def _load_catalog(db: Session, organization_id: int) -> tuple[Catalog, _CatalogIndex]:
    categories = list(
        db.scalars(
            select(Category)
            .where(Category.organization_id == organization_id, Category.is_active.is_(True))
            .options(selectinload(Category.subcategories), selectinload(Category.default_team))
        )
    )
    teams = list(db.scalars(select(Team).where(Team.organization_id == organization_id)))

    index = _CatalogIndex()
    catalog_categories = []
    for category in categories:
        index.categories[normalize(category.name)] = category
        active_subs = [sub for sub in category.subcategories if sub.is_active]
        for sub in active_subs:
            index.subcategories[(category.id, normalize(sub.name))] = sub
        catalog_categories.append(
            CatalogCategory(
                name=category.name,
                description=category.description,
                subcategories=tuple(sub.name for sub in active_subs),
            )
        )
    for team in teams:
        index.teams[normalize(team.name)] = team

    catalog = Catalog(
        categories=tuple(catalog_categories),
        teams=tuple(CatalogTeam(name=team.name, description=team.description) for team in teams),
    )
    return catalog, index
