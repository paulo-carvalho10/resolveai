from datetime import date

from pydantic import BaseModel


class Indicators(BaseModel):
    """Current state of the queue (not limited to the period)."""

    open: int
    in_progress: int
    waiting_user: int
    critical_open: int
    sla_at_risk: int
    sla_breached_open: int
    resolved_today: int


class PeriodMetrics(BaseModel):
    days: int
    created: int
    resolved: int
    # Share of tickets created in the period that are already resolved or closed.
    resolution_rate: float | None
    avg_first_response_hours: float | None
    avg_resolution_hours: float | None
    sla_met: int
    sla_breached: int


class CountItem(BaseModel):
    label: str
    count: int


class DurationItem(BaseModel):
    label: str
    avg_hours: float
    tickets: int


class DailyPoint(BaseModel):
    date: date
    created: int
    resolved: int


class ArticleUsage(BaseModel):
    article_id: int | None
    code: str
    title: str
    citations: int


class AIMetrics(BaseModel):
    analyses: int
    failed_analyses: int
    # Among tickets with an AI suggestion and a final value: how often the final value matches.
    category_acceptance: float | None
    priority_acceptance: float | None
    avg_confidence: float | None
    auto_applied: int
    suggestions: int
    suggestions_answered: int
    estimated_minutes_saved: float
    top_articles: list[ArticleUsage]


class Dashboard(BaseModel):
    generated_at: str
    timezone: str
    indicators: Indicators
    period: PeriodMetrics
    by_category: list[CountItem]
    by_priority: list[CountItem]
    by_team: list[CountItem]
    by_status: list[CountItem]
    daily: list[DailyPoint]
    resolution_by_category: list[DurationItem]
    ai: AIMetrics
