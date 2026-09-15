from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, enum_column, utcnow
from app.models.enums import AnalysisStatus, TicketPriority

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class PriorityRule(TimestampMixin, Base):
    """Deterministic business rule: if a ticket mentions any keyword, raise its priority."""

    __tablename__ = "priority_rules"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    keywords: Mapped[list[str]] = mapped_column(JSON)
    priority: Mapped[TicketPriority] = mapped_column(enum_column(TicketPriority))
    is_active: Mapped[bool] = mapped_column(default=True)


class TicketAIAnalysis(Base):
    """One classification run. Keeps the raw suggestion, what was applied, and the cost."""

    __tablename__ = "ticket_ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    # Null when the analysis ran automatically on ticket creation.
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[AnalysisStatus] = mapped_column(enum_column(AnalysisStatus))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(60))

    category_name: Mapped[str | None] = mapped_column(String(80))
    subcategory_name: Mapped[str | None] = mapped_column(String(80))
    team_name: Mapped[str | None] = mapped_column(String(80))
    priority: Mapped[TicketPriority | None] = mapped_column(enum_column(TicketPriority))
    urgency: Mapped[TicketPriority | None] = mapped_column(enum_column(TicketPriority))
    summary: Mapped[str | None] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None]

    matched_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("priority_rules.id", ondelete="SET NULL")
    )
    # Comma-separated ticket fields this run changed, e.g. "category,subcategory,team".
    applied_fields: Mapped[str | None] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(50))

    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    ticket: Mapped["Ticket"] = relationship(back_populates="ai_analyses")
    requested_by: Mapped["User | None"] = relationship()
    matched_rule: Mapped[PriorityRule | None] = relationship()
