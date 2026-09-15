from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Query, Response, status

from app.api.deps import AdminUser, CurrentUser, DbSession, EmbedderDep, SessionFactory
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import KnowledgeArticle
from app.schemas.common import Page
from app.schemas.knowledge import (
    ArticleCreate,
    ArticleFilters,
    ArticleRead,
    ArticleSummary,
    ArticleUpdate,
    ReindexResult,
    SearchHit,
)
from app.services import knowledge_service
from app.services.embeddings import EmbeddingError

router = APIRouter(prefix="/knowledge", tags=["knowledge base"])

_EXCERPT_CHARS = 280


@router.get("", response_model=Page[ArticleSummary])
def list_articles(
    actor: CurrentUser, db: DbSession, filters: Annotated[ArticleFilters, Query()]
) -> dict[str, Any]:
    """Requesters only see published articles; agents and admins also see drafts and archived."""
    items, total = knowledge_service.list_articles(db, actor, filters)
    return {"items": items, "total": total, "page": filters.page, "page_size": filters.page_size}


@router.get("/search", response_model=list[SearchHit])
def search_articles(
    actor: CurrentUser,
    db: DbSession,
    embedder: EmbedderDep,
    q: Annotated[str, Query(min_length=3, max_length=2000)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[dict[str, Any]]:
    """Semantic search over published articles, ranked by similarity."""
    try:
        results = knowledge_service.search(
            db,
            actor.organization_id,
            q,
            embedder,
            limit=limit,
            min_score=get_settings().effective_rag_min_score,
        )
    except EmbeddingError as exc:
        raise AppError(exc.code, "Search is temporarily unavailable.", 502) from exc
    return [
        {
            "article": item.article,
            "score": round(item.score, 4),
            "excerpt": _excerpt(item.chunks[0].chunk.content),
        }
        for item in results
    ]


@router.post("/reindex", response_model=ReindexResult, status_code=status.HTTP_202_ACCEPTED)
def reindex(
    actor: AdminUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    embedder: EmbedderDep,
    session_factory: SessionFactory,
) -> ReindexResult:
    """Re-embed every article, e.g. after switching EMBEDDING_PROVIDER or EMBEDDING_MODEL."""
    article_ids = knowledge_service.mark_all_for_reindex(db, actor.organization_id)
    background_tasks.add_task(
        knowledge_service.index_in_background, session_factory, embedder, article_ids
    )
    return ReindexResult(articles=len(article_ids))


@router.post("", response_model=ArticleRead, status_code=status.HTTP_201_CREATED)
def create_article(
    data: ArticleCreate,
    actor: AdminUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    embedder: EmbedderDep,
    session_factory: SessionFactory,
) -> KnowledgeArticle:
    """The article is indexed for search in the background (see `index_status`)."""
    article = knowledge_service.create_article(db, actor, data)
    background_tasks.add_task(
        knowledge_service.index_in_background, session_factory, embedder, [article.id]
    )
    return article


@router.get("/{article_id}", response_model=ArticleRead)
def get_article(article_id: int, actor: CurrentUser, db: DbSession) -> KnowledgeArticle:
    return knowledge_service.get_article(db, actor, article_id)


@router.patch("/{article_id}", response_model=ArticleRead)
def update_article(
    article_id: int,
    data: ArticleUpdate,
    actor: AdminUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    embedder: EmbedderDep,
    session_factory: SessionFactory,
) -> KnowledgeArticle:
    article, needs_reindex = knowledge_service.update_article(db, actor, article_id, data)
    if needs_reindex:
        background_tasks.add_task(
            knowledge_service.index_in_background, session_factory, embedder, [article.id]
        )
    return article


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(article_id: int, actor: AdminUser, db: DbSession) -> Response:
    knowledge_service.delete_article(db, actor, article_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _excerpt(text: str) -> str:
    if len(text) <= _EXCERPT_CHARS:
        return text
    return text[:_EXCERPT_CHARS].rsplit(" ", 1)[0] + "..."
