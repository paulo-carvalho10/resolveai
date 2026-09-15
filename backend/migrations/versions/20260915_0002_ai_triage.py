"""ai triage: priority rules, ticket AI analyses and AI suggestion fields on tickets

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "priority_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name"),
    )
    op.create_index("ix_priority_rules_organization_id", "priority_rules", ["organization_id"])

    op.create_table(
        "ticket_ai_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(60), nullable=False),
        sa.Column("category_name", sa.String(80), nullable=True),
        sa.Column("subcategory_name", sa.String(80), nullable=True),
        sa.Column("team_name", sa.String(80), nullable=True),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("urgency", sa.String(20), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "matched_rule_id",
            sa.Integer(),
            sa.ForeignKey("priority_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("applied_fields", sa.String(100), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_ai_analyses_ticket_id", "ticket_ai_analyses", ["ticket_id"])

    op.add_column("tickets", sa.Column("ai_category_id", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("ai_subcategory_id", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("ai_team_id", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("ai_priority", sa.String(20), nullable=True))
    op.add_column("tickets", sa.Column("ai_confidence", sa.Float(), nullable=True))
    op.add_column("tickets", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("ai_analyzed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_tickets_ai_category_id_categories",
        "tickets",
        "categories",
        ["ai_category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tickets_ai_subcategory_id_subcategories",
        "tickets",
        "subcategories",
        ["ai_subcategory_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tickets_ai_team_id_teams",
        "tickets",
        "teams",
        ["ai_team_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tickets_ai_team_id_teams", "tickets", type_="foreignkey")
    op.drop_constraint("fk_tickets_ai_subcategory_id_subcategories", "tickets", type_="foreignkey")
    op.drop_constraint("fk_tickets_ai_category_id_categories", "tickets", type_="foreignkey")
    for column in (
        "ai_analyzed_at",
        "ai_summary",
        "ai_confidence",
        "ai_priority",
        "ai_team_id",
        "ai_subcategory_id",
        "ai_category_id",
    ):
        op.drop_column("tickets", column)
    op.drop_table("ticket_ai_analyses")
    op.drop_table("priority_rules")
