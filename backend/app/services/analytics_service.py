"""Dashboard metrics for an organization.

Current-state indicators come from COUNT queries. Period metrics load the period's rows once and
aggregate in Python: time differences and timezone-aware days behave the same on PostgreSQL and
SQLite, and a few thousand rows per period are cheap.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import fmean
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, aliased

from app.core.config import get_settings
from app.models import (
    AnalysisStatus,
    Category,
    Team,
    Ticket,
    TicketAIAnalysis,
    TicketEventType,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    TicketSuggestion,
    TicketSuggestionSource,
)
from app.models.base import utcnow
from app.schemas.analytics import (
    AIMetrics,
    ArticleUsage,
    CountItem,
    DailyPoint,
    Dashboard,
    DurationItem,
    Indicators,
    PeriodMetrics,
)
from app.services import sla

UNCATEGORIZED = "Sem categoria"
UNASSIGNED_TEAM = "Sem equipe"
ACTIVE_STATUSES = (TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_USER)
DONE_STATUSES = (TicketStatus.RESOLVED, TicketStatus.CLOSED)


@dataclass
class _Row:
    id: int
    status: TicketStatus
    priority: TicketPriority
    category: str | None
    team: str | None
    created_at: datetime
    resolved_at: datetime | None
    category_id: int | None
    ai_category_id: int | None
    ai_priority: TicketPriority | None


def build_dashboard(db: Session, organization_id: int, days: int) -> Dashboard:
    settings = get_settings()
    zone = ZoneInfo(settings.timezone)
    now = utcnow()
    since = now - timedelta(days=days)

    rows = _period_rows(db, organization_id, since)
    resolved_rows = [r for r in rows if r.resolved_at is not None and r.resolved_at >= since]
    resolved_in_period = _resolved_in_period(db, organization_id, since)

    return Dashboard(
        generated_at=now.isoformat(),
        timezone=settings.timezone,
        indicators=_indicators(db, organization_id, now, zone),
        period=PeriodMetrics(
            days=days,
            created=len(rows),
            resolved=len(resolved_in_period),
            resolution_rate=_ratio(sum(r.status in DONE_STATUSES for r in rows), len(rows)),
            avg_first_response_hours=_avg_first_response_hours(db, rows),
            avg_resolution_hours=_avg_hours(resolved_rows),
            sla_met=sum(_sla(r) == sla.SlaStatus.MET for r in resolved_in_period),
            sla_breached=sum(_sla(r) == sla.SlaStatus.BREACHED for r in resolved_in_period),
        ),
        by_category=_counts(r.category or UNCATEGORIZED for r in rows),
        by_priority=[
            CountItem(label=p.value, count=sum(r.priority == p for r in rows))
            for p in TicketPriority
        ],
        by_team=_counts(r.team or UNASSIGNED_TEAM for r in rows),
        by_status=[
            CountItem(label=s.value, count=sum(r.status == s for r in rows)) for s in TicketStatus
        ],
        daily=_daily(rows, resolved_in_period, since, now, zone),
        resolution_by_category=_resolution_by_category(resolved_rows),
        ai=_ai_metrics(db, organization_id, rows, since),
    )


# --- Loading -------------------------------------------------------------------------------


def _row_query(organization_id: int) -> Select[tuple]:
    return (
        select(
            Ticket.id,
            Ticket.status,
            Ticket.priority,
            Category.name,
            Team.name,
            Ticket.created_at,
            Ticket.resolved_at,
            Ticket.category_id,
            Ticket.ai_category_id,
            Ticket.ai_priority,
        )
        .select_from(Ticket)
        .outerjoin(Category, Category.id == Ticket.category_id)
        .outerjoin(Team, Team.id == Ticket.team_id)
        .where(Ticket.organization_id == organization_id)
    )


def _period_rows(db: Session, organization_id: int, since: datetime) -> list[_Row]:
    stmt = _row_query(organization_id).where(Ticket.created_at >= since)
    return [_Row(*row) for row in db.execute(stmt)]


def _resolved_in_period(db: Session, organization_id: int, since: datetime) -> list[_Row]:
    """Tickets resolved in the period, including ones created before it."""
    stmt = _row_query(organization_id).where(Ticket.resolved_at >= since)
    return [_Row(*row) for row in db.execute(stmt)]


# --- Indicators ----------------------------------------------------------------------------


def _indicators(db: Session, organization_id: int, now: datetime, zone: ZoneInfo) -> Indicators:
    status_counts = dict(
        db.execute(
            select(Ticket.status, func.count())
            .where(Ticket.organization_id == organization_id)
            .group_by(Ticket.status)
        ).all()
    )
    active = db.execute(
        select(Ticket.priority, Ticket.status, Ticket.created_at).where(
            Ticket.organization_id == organization_id, Ticket.status.in_(ACTIVE_STATUSES)
        )
    ).all()
    sla_states = Counter(
        sla.status(priority, status, created_at, None, now)
        for priority, status, created_at in active
    )
    start_of_today = datetime.combine(now.astimezone(zone).date(), datetime.min.time(), zone)
    resolved_today = db.scalar(
        select(func.count()).where(
            Ticket.organization_id == organization_id, Ticket.resolved_at >= start_of_today
        )
    )
    return Indicators(
        open=status_counts.get(TicketStatus.OPEN, 0),
        in_progress=status_counts.get(TicketStatus.IN_PROGRESS, 0),
        waiting_user=status_counts.get(TicketStatus.WAITING_USER, 0),
        critical_open=sum(priority == TicketPriority.CRITICAL for priority, _, _ in active),
        sla_at_risk=sla_states[sla.SlaStatus.AT_RISK],
        sla_breached_open=sla_states[sla.SlaStatus.BREACHED],
        resolved_today=resolved_today or 0,
    )


# --- Period aggregations -------------------------------------------------------------------


def _sla(row: _Row) -> sla.SlaStatus:
    return sla.status(row.priority, row.status, row.created_at, row.resolved_at)


def _hours(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600


def _avg_hours(rows: list[_Row]) -> float | None:
    durations = [_hours(r.created_at, r.resolved_at) for r in rows if r.resolved_at is not None]
    return round(fmean(durations), 2) if durations else None


def _avg_first_response_hours(db: Session, rows: list[_Row]) -> float | None:
    """Time until a person first took the ticket (first assignment)."""
    if not rows:
        return None
    created = {r.id: r.created_at for r in rows}
    first_assignment = db.execute(
        select(TicketHistory.ticket_id, func.min(TicketHistory.created_at))
        .where(
            TicketHistory.ticket_id.in_(created),
            TicketHistory.event_type == TicketEventType.ASSIGNEE_CHANGED,
        )
        .group_by(TicketHistory.ticket_id)
    ).all()
    durations = [
        _hours(created[ticket_id], _aware(assigned_at))
        for ticket_id, assigned_at in first_assignment
    ]
    return round(fmean(durations), 2) if durations else None


def _aware(value: datetime) -> datetime:
    """Aggregates like MIN() bypass the column type, so SQLite returns naive UTC datetimes."""
    return value if value.tzinfo is not None else value.replace(tzinfo=ZoneInfo("UTC"))


def _counts(labels: object) -> list[CountItem]:
    counter: Counter[str] = Counter(labels)  # type: ignore[arg-type]
    return [CountItem(label=label, count=count) for label, count in counter.most_common()]


def _daily(
    created_rows: list[_Row],
    resolved_rows: list[_Row],
    since: datetime,
    now: datetime,
    zone: ZoneInfo,
) -> list[DailyPoint]:
    created = Counter(r.created_at.astimezone(zone).date() for r in created_rows)
    resolved = Counter(
        r.resolved_at.astimezone(zone).date() for r in resolved_rows if r.resolved_at is not None
    )
    first, last = since.astimezone(zone).date(), now.astimezone(zone).date()
    days: list[date] = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return [DailyPoint(date=d, created=created[d], resolved=resolved[d]) for d in days]


def _resolution_by_category(rows: list[_Row]) -> list[DurationItem]:
    grouped: defaultdict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.resolved_at is not None:
            grouped[r.category or UNCATEGORIZED].append(_hours(r.created_at, r.resolved_at))
    items = [
        DurationItem(label=label, avg_hours=round(fmean(values), 2), tickets=len(values))
        for label, values in grouped.items()
    ]
    return sorted(items, key=lambda item: item.avg_hours, reverse=True)


def _ai_metrics(db: Session, organization_id: int, rows: list[_Row], since: datetime) -> AIMetrics:
    settings = get_settings()
    ticket_ids = [r.id for r in rows]

    analyses = db.execute(
        select(
            TicketAIAnalysis.status, TicketAIAnalysis.confidence, TicketAIAnalysis.applied_fields
        )
        .join(Ticket)
        .where(Ticket.organization_id == organization_id, TicketAIAnalysis.created_at >= since)
    ).all()
    succeeded = [a for a in analyses if a.status == AnalysisStatus.SUCCEEDED]
    auto_applied = sum(1 for a in succeeded if a.applied_fields)

    with_category = [r for r in rows if r.ai_category_id is not None and r.category_id is not None]
    with_priority = [r for r in rows if r.ai_priority is not None]

    suggestion_counts = db.execute(
        select(func.count(), func.count().filter(TicketSuggestion.can_answer.is_(True)))
        .join(Ticket)
        .where(Ticket.organization_id == organization_id, TicketSuggestion.created_at >= since)
    ).one()

    source = aliased(TicketSuggestionSource)
    top = (
        db.execute(
            select(source.article_id, source.article_code, source.article_title, func.count())
            .join(TicketSuggestion, TicketSuggestion.id == source.suggestion_id)
            .where(TicketSuggestion.ticket_id.in_(ticket_ids), source.cited.is_(True))
            .group_by(source.article_id, source.article_code, source.article_title)
            .order_by(func.count().desc())
            .limit(5)
        ).all()
        if ticket_ids
        else []
    )

    answered = suggestion_counts[1] or 0
    return AIMetrics(
        analyses=len(analyses),
        failed_analyses=len(analyses) - len(succeeded),
        category_acceptance=_ratio(
            sum(r.category_id == r.ai_category_id for r in with_category), len(with_category)
        ),
        priority_acceptance=_ratio(
            sum(r.priority == r.ai_priority for r in with_priority), len(with_priority)
        ),
        avg_confidence=(
            round(fmean(a.confidence for a in succeeded if a.confidence is not None), 3)
            if any(a.confidence is not None for a in succeeded)
            else None
        ),
        auto_applied=auto_applied,
        suggestions=suggestion_counts[0] or 0,
        suggestions_answered=answered,
        estimated_minutes_saved=round(
            auto_applied * settings.minutes_saved_per_applied_triage
            + answered * settings.minutes_saved_per_answered_suggestion,
            1,
        ),
        top_articles=[
            ArticleUsage(article_id=article_id, code=code, title=title, citations=count)
            for article_id, code, title, count in top
        ],
    )


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None
