from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, Dialect, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, TypeEngine

from app.models.base import Base, TimestampMixin, UTCDateTime, enum_column, utcnow
from app.models.enums import AnalysisStatus, ArticleStatus, IndexStatus

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.ticket import Ticket
    from app.models.user import User

# Fixed by migration 0003. Changing it requires a migration and re-indexing every article.
EMBEDDING_DIMENSIONS = 1024


class EmbeddingVector(TypeDecorator[list[float]]):
    """pgvector `vector(n)` on PostgreSQL; JSON on SQLite so the test suite runs anywhere."""

    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[object]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(VECTOR(self.dimensions))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[float] | None, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        if len(value) != self.dimensions:
            raise ValueError(f"Expected {self.dimensions} dimensions, got {len(value)}.")
        return [float(component) for component in value]

    def process_result_value(self, value: object, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        return [float(component) for component in value]  # type: ignore[attr-defined]


class KnowledgeArticle(TimestampMixin, Base):
    __tablename__ = "knowledge_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    # Normalized: lowercase, no accents, hyphens instead of spaces (e.g. "nfe", "rejeicao-539").
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[ArticleStatus] = mapped_column(
        enum_column(ArticleStatus), default=ArticleStatus.DRAFT, index=True
    )
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    index_status: Mapped[IndexStatus] = mapped_column(
        enum_column(IndexStatus), default=IndexStatus.PENDING
    )
    index_error: Mapped[str | None] = mapped_column(String(50))
    indexed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    category: Mapped["Category | None"] = relationship()
    author: Mapped["User | None"] = relationship()
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="KnowledgeChunk.position",
    )

    @property
    def code(self) -> str:
        return article_code(self.id)


def article_code(article_id: int) -> str:
    """Human-friendly reference used in answers and citations, e.g. KB-023."""
    return f"KB-{article_id:03d}"


class KnowledgeChunk(Base):
    """A passage of an article with its embedding. One article has one or more chunks."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True
    )
    # Denormalized so vector search can filter by tenant without a join on the hot path.
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector(EMBEDDING_DIMENSIONS))
    # Vectors from different models are not comparable; search only uses the current model's.
    embedding_model: Mapped[str] = mapped_column(String(60), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    article: Mapped[KnowledgeArticle] = relationship(back_populates="chunks")


class TicketSuggestion(Base):
    """A RAG answer suggested for a ticket, with the articles it was grounded on."""

    __tablename__ = "ticket_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[AnalysisStatus] = mapped_column(enum_column(AnalysisStatus))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(60))
    embedding_model: Mapped[str | None] = mapped_column(String(60))
    # False when the knowledge base does not cover the ticket.
    can_answer: Mapped[bool | None]
    answer: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(50))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    ticket: Mapped["Ticket"] = relationship()
    requested_by: Mapped["User | None"] = relationship()
    sources: Mapped[list["TicketSuggestionSource"]] = relationship(
        back_populates="suggestion",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TicketSuggestionSource.rank",
    )


class TicketSuggestionSource(Base):
    """An article retrieved for a suggestion. `cited` marks the ones the answer relied on."""

    __tablename__ = "ticket_suggestion_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    suggestion_id: Mapped[int] = mapped_column(
        ForeignKey("ticket_suggestions.id", ondelete="CASCADE"), index=True
    )
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="SET NULL"), index=True
    )
    # Snapshots, so a suggestion still reads correctly after the article changes or is deleted.
    article_code: Mapped[str] = mapped_column(String(20))
    article_title: Mapped[str] = mapped_column(String(200))
    rank: Mapped[int]
    score: Mapped[float]
    cited: Mapped[bool] = mapped_column(default=False)

    suggestion: Mapped[TicketSuggestion] = relationship(back_populates="sources")
    article: Mapped[KnowledgeArticle | None] = relationship()
