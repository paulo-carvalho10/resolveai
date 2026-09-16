"""requester resolution: who resolved a ticket, and messages that describe a solution

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("resolved_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tickets_resolved_by_id_users",
        "tickets",
        "users",
        ["resolved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "ticket_messages",
        sa.Column("is_solution", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Tickets resolved before this column existed: the audit trail knows who resolved them.
    op.execute(
        """
        UPDATE tickets SET resolved_by_id = (
            SELECT h.actor_id FROM ticket_history h
            WHERE h.ticket_id = tickets.id AND h.event_type = 'RESOLVED'
            ORDER BY h.created_at DESC, h.id DESC
            LIMIT 1
        )
        WHERE resolved_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("ticket_messages", "is_solution")
    op.drop_constraint("fk_tickets_resolved_by_id_users", "tickets", type_="foreignkey")
    op.drop_column("tickets", "resolved_by_id")
