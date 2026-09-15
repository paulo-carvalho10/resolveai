"""Knowledge base: articles, chunking, embedding indexing and vector search."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Float, String, cast, delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError
from app.core.logger import log_event
from app.core.text import slugify
from app.models import (
    ArticleStatus,
    IndexStatus,
    KnowledgeArticle,
    KnowledgeChunk,
    User,
)
from app.models.base import utcnow
from app.schemas.knowledge import ArticleCreate, ArticleFilters, ArticleUpdate
from app.services import category_service
from app.services.embeddings import Embedder, EmbeddingError, cosine_similarity

logger = logging.getLogger(__name__)

CHUNK_MAX_CHARS = 1200
CHUNK_OVERLAP_CHARS = 200


# --- Articles ------------------------------------------------------------------------------


def _visible_to(actor: User) -> list[ColumnElement[bool]]:
    """Requesters only see published articles (self-service); staff see drafts too."""
    conditions = [KnowledgeArticle.organization_id == actor.organization_id]
    if not actor.is_staff:
        conditions.append(KnowledgeArticle.status == ArticleStatus.PUBLISHED)
    return conditions


def list_articles(
    db: Session, actor: User, filters: ArticleFilters
) -> tuple[list[KnowledgeArticle], int]:
    stmt = select(KnowledgeArticle).where(*_visible_to(actor))
    if filters.status is not None:
        stmt = stmt.where(KnowledgeArticle.status == filters.status)
    if filters.category_id is not None:
        stmt = stmt.where(KnowledgeArticle.category_id == filters.category_id)
    if filters.tag:
        # Tags are stored normalized (ASCII slugs) in a JSON list, so a quoted match on the
        # serialized list is exact and works on both PostgreSQL and SQLite.
        stmt = stmt.where(cast(KnowledgeArticle.tags, String).contains(f'"{slugify(filters.tag)}"'))
    if filters.q and (term := filters.q.strip()):
        stmt = stmt.where(
            or_(
                KnowledgeArticle.title.icontains(term, autoescape=True),
                KnowledgeArticle.content.icontains(term, autoescape=True),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = (
        stmt.options(selectinload(KnowledgeArticle.category), selectinload(KnowledgeArticle.author))
        .order_by(KnowledgeArticle.updated_at.desc(), KnowledgeArticle.id.desc())
        .offset(filters.offset)
        .limit(filters.page_size)
    )
    return list(db.scalars(stmt)), total


def get_article(db: Session, actor: User, article_id: int) -> KnowledgeArticle:
    article = db.scalar(
        select(KnowledgeArticle)
        .where(KnowledgeArticle.id == article_id, *_visible_to(actor))
        .options(selectinload(KnowledgeArticle.category), selectinload(KnowledgeArticle.author))
    )
    if article is None:
        raise NotFoundError("Article")
    return article


def create_article(db: Session, author: User, data: ArticleCreate) -> KnowledgeArticle:
    if data.category_id is not None:
        category_service.get_category(db, author.organization_id, data.category_id)
    article = KnowledgeArticle(
        organization_id=author.organization_id,
        title=data.title,
        content=data.content,
        category_id=data.category_id,
        tags=data.tags,
        status=data.status,
        author=author,
        index_status=IndexStatus.PENDING,
    )
    db.add(article)
    db.commit()
    log_event(logger, "knowledge.article_created", article_id=article.id, user_id=author.id)
    return get_article(db, author, article.id)


def update_article(
    db: Session, actor: User, article_id: int, data: ArticleUpdate
) -> tuple[KnowledgeArticle, bool]:
    """Returns the article and whether its text changed (and therefore needs re-indexing)."""
    article = get_article(db, actor, article_id)
    changes = data.model_dump(exclude_unset=True)

    needs_reindex = False
    for field in ("title", "content"):
        if changes.get(field) is not None and changes[field] != getattr(article, field):
            setattr(article, field, changes[field])
            needs_reindex = True
    if "category_id" in changes:
        if changes["category_id"] is not None:
            category_service.get_category(db, actor.organization_id, changes["category_id"])
        article.category_id = changes["category_id"]
    if changes.get("tags") is not None:
        article.tags = changes["tags"]
    if changes.get("status") is not None:
        article.status = changes["status"]
    if needs_reindex:
        article.index_status = IndexStatus.PENDING

    db.commit()
    log_event(logger, "knowledge.article_updated", article_id=article.id, user_id=actor.id)
    return get_article(db, actor, article.id), needs_reindex


def delete_article(db: Session, actor: User, article_id: int) -> None:
    article = get_article(db, actor, article_id)
    db.delete(article)
    db.commit()
    log_event(logger, "knowledge.article_deleted", article_id=article_id, user_id=actor.id)


# --- Chunking and indexing -----------------------------------------------------------------


def chunk_text(
    content: str, max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP_CHARS
) -> list[str]:
    """Split on paragraph boundaries into chunks of at most ~max_chars.

    Paragraphs are kept whole when possible so a step-by-step solution is not cut in half.
    A paragraph longer than max_chars is split on whitespace with `overlap` characters repeated
    between pieces, so a sentence on the boundary is fully present in at least one chunk.
    """
    paragraphs = [p.strip() for p in content.replace("\r\n", "\n").split("\n\n") if p.strip()]
    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
            continue
        start = 0
        while start < len(paragraph):
            end = min(start + max_chars, len(paragraph))
            if end < len(paragraph):
                space = paragraph.rfind(" ", start + max_chars // 2, end)
                end = space if space != -1 else end
            pieces.append(paragraph[start:end].strip())
            if end >= len(paragraph):
                break
            start = max(end - overlap, start + 1)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def index_article(db: Session, article: KnowledgeArticle, embedder: Embedder) -> None:
    """Replace the article's chunks with freshly embedded ones. Never raises on provider errors."""
    chunks = chunk_text(article.content)
    # The title gives every chunk its context ("Rejeição 539" + the step it describes).
    texts = [f"{article.title}\n\n{chunk}" for chunk in chunks]
    try:
        batch = embedder.embed(texts, input_type="document")
    except EmbeddingError as exc:
        article.index_status = IndexStatus.FAILED
        article.index_error = exc.code
        db.commit()
        log_event(
            logger,
            "knowledge.index_failed",
            level=logging.ERROR,
            article_id=article.id,
            error=exc.code,
        )
        return

    db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.article_id == article.id))
    for position, (chunk, vector) in enumerate(zip(chunks, batch.vectors, strict=True)):
        db.add(
            KnowledgeChunk(
                article_id=article.id,
                organization_id=article.organization_id,
                position=position,
                content=chunk,
                embedding=vector,
                embedding_model=embedder.model,
            )
        )
    article.index_status = IndexStatus.INDEXED
    article.index_error = None
    article.indexed_at = utcnow()
    db.commit()
    log_event(
        logger,
        "knowledge.article_indexed",
        article_id=article.id,
        chunks=len(chunks),
        model=embedder.model,
        tokens=batch.total_tokens,
    )


def index_in_background(
    session_factory: Callable[[], Session], embedder: Embedder, article_ids: list[int]
) -> None:
    for article_id in article_ids:
        try:
            with session_factory() as db:
                article = db.get(KnowledgeArticle, article_id)
                if article is not None:
                    index_article(db, article, embedder)
        except Exception as exc:
            log_event(
                logger,
                "knowledge.index_crashed",
                level=logging.ERROR,
                exc_info=exc,
                article_id=article_id,
            )


def mark_all_for_reindex(db: Session, organization_id: int) -> list[int]:
    articles = list(
        db.scalars(
            select(KnowledgeArticle).where(KnowledgeArticle.organization_id == organization_id)
        )
    )
    for article in articles:
        article.index_status = IndexStatus.PENDING
    db.commit()
    return [article.id for article in articles]


# --- Search --------------------------------------------------------------------------------


@dataclass
class ScoredChunk:
    chunk: KnowledgeChunk
    score: float


@dataclass
class RetrievedArticle:
    article: KnowledgeArticle
    score: float
    chunks: list[ScoredChunk]


def search(
    db: Session,
    organization_id: int,
    query: str,
    embedder: Embedder,
    limit: int,
    min_score: float,
) -> list[RetrievedArticle]:
    """Semantic search over published articles, best article first.

    Raises EmbeddingError when the query itself cannot be embedded.
    """
    query_vector = embedder.embed([query], input_type="query").vectors[0]
    candidates = _nearest_chunks(db, organization_id, query_vector, embedder.model, limit * 4)

    by_article: dict[int, RetrievedArticle] = {}
    for scored in candidates:
        if scored.score < min_score:
            continue
        entry = by_article.get(scored.chunk.article_id)
        if entry is None:
            by_article[scored.chunk.article_id] = RetrievedArticle(
                article=scored.chunk.article, score=scored.score, chunks=[scored]
            )
        elif len(entry.chunks) < 3:
            entry.chunks.append(scored)
    ranked = sorted(by_article.values(), key=lambda item: item.score, reverse=True)
    return ranked[:limit]


def _nearest_chunks(
    db: Session, organization_id: int, vector: list[float], model: str, limit: int
) -> list[ScoredChunk]:
    base = (
        select(KnowledgeChunk)
        .join(KnowledgeArticle)
        .where(
            KnowledgeChunk.organization_id == organization_id,
            KnowledgeChunk.embedding_model == model,
            KnowledgeArticle.status == ArticleStatus.PUBLISHED,
        )
        .options(selectinload(KnowledgeChunk.article).selectinload(KnowledgeArticle.category))
    )

    if db.get_bind().dialect.name == "postgresql":
        # pgvector: <=> is cosine distance, served by the HNSW index.
        distance = KnowledgeChunk.embedding.op("<=>", return_type=Float())(vector)
        rows = db.execute(
            base.add_columns(distance.label("distance")).order_by(distance).limit(limit)
        ).all()
        return [ScoredChunk(chunk=row[0], score=1.0 - float(row.distance)) for row in rows]

    # SQLite (tests): same ranking computed in Python.
    scored = [
        ScoredChunk(chunk=chunk, score=cosine_similarity(chunk.embedding, vector))
        for chunk in db.scalars(base)
    ]
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]
