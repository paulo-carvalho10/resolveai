from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, enum_column, utcnow
from app.models.enums import TicketEventType, TicketPriority, TicketStatus

if TYPE_CHECKING:
    from app.models.ai import TicketAIAnalysis
    from app.models.category import Category, Subcategory
    from app.models.team import Team
    from app.models.user import User


class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_organization_id_created_at", "organization_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(
        enum_column(TicketStatus), default=TicketStatus.OPEN, index=True
    )
    priority: Mapped[TicketPriority] = mapped_column(
        enum_column(TicketPriority), default=TicketPriority.MEDIUM, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    subcategory_id: Mapped[int | None] = mapped_column(
        ForeignKey("subcategories.id", ondelete="SET NULL")
    )
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Who resolved it. Equal to the requester when they solved it without the team.
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # Latest AI suggestion, kept even when it was not applied, so humans can compare.
    ai_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    ai_subcategory_id: Mapped[int | None] = mapped_column(
        ForeignKey("subcategories.id", ondelete="SET NULL")
    )
    ai_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    ai_priority: Mapped[TicketPriority | None] = mapped_column(enum_column(TicketPriority))
    ai_confidence: Mapped[float | None]
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    requester: Mapped["User"] = relationship(foreign_keys=[requester_id])
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assignee_id])
    resolved_by: Mapped["User | None"] = relationship(foreign_keys=[resolved_by_id])
    team: Mapped["Team | None"] = relationship(foreign_keys=[team_id])
    category: Mapped["Category | None"] = relationship(foreign_keys=[category_id])
    subcategory: Mapped["Subcategory | None"] = relationship(foreign_keys=[subcategory_id])
    ai_team: Mapped["Team | None"] = relationship(foreign_keys=[ai_team_id])
    ai_category: Mapped["Category | None"] = relationship(foreign_keys=[ai_category_id])
    ai_subcategory: Mapped["Subcategory | None"] = relationship(foreign_keys=[ai_subcategory_id])
    ai_analyses: Mapped[list["TicketAIAnalysis"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TicketAIAnalysis.id",
    )
    messages: Mapped[list["TicketMessage"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", passive_deletes=True
    )
    history: Mapped[list["TicketHistory"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", passive_deletes=True
    )


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    # Internal notes are only visible to agents and admins.
    is_internal: Mapped[bool] = mapped_column(default=False)
    # The requester's account of how they solved the problem, for the team to review.
    is_solution: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="messages")
    author: Mapped["User"] = relationship()


class TicketHistory(Base):
    """Audit trail entry. Values are display labels captured when the event happened."""

    __tablename__ = "ticket_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    # Null actor means the system (rules engine, AI) made the change.
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[TicketEventType] = mapped_column(enum_column(TicketEventType, length=30))
    field: Mapped[str | None] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="history")
    actor: Mapped["User | None"] = relationship()
