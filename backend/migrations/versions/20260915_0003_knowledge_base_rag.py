"""knowledge base and RAG: articles, embedded chunks (pgvector), ticket suggestions

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("index_status", sa.String(20), nullable=False),
        sa.Column("index_error", sa.String(50), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_knowledge_articles_organization_id", "knowledge_articles", ["organization_id"]
    )
    op.create_index("ix_knowledge_articles_category_id", "knowledge_articles", ["category_id"])
    op.create_index("ix_knowledge_articles_status", "knowledge_articles", ["status"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "article_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", VECTOR(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("embedding_model", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_chunks_article_id", "knowledge_chunks", ["article_id"])
    op.create_index("ix_knowledge_chunks_organization_id", "knowledge_chunks", ["organization_id"])
    op.create_index("ix_knowledge_chunks_embedding_model", "knowledge_chunks", ["embedding_model"])
    # Approximate nearest-neighbour index for cosine distance (<=>).
    op.create_index(
        "ix_knowledge_chunks_embedding_hnsw",
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "ticket_suggestions",
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
        sa.Column("embedding_model", sa.String(60), nullable=True),
        sa.Column("can_answer", sa.Boolean(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_suggestions_ticket_id", "ticket_suggestions", ["ticket_id"])

    op.create_table(
        "ticket_suggestion_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "suggestion_id",
            sa.Integer(),
            sa.ForeignKey("ticket_suggestions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "article_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("article_code", sa.String(20), nullable=False),
        sa.Column("article_title", sa.String(200), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("cited", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_ticket_suggestion_sources_suggestion_id", "ticket_suggestion_sources", ["suggestion_id"]
    )
    op.create_index(
        "ix_ticket_suggestion_sources_article_id", "ticket_suggestion_sources", ["article_id"]
    )


def downgrade() -> None:
    op.drop_table("ticket_suggestion_sources")
    op.drop_table("ticket_suggestions")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_articles")
    # The vector extension is left installed: other database objects may depend on it.
