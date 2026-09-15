from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.core.text import slugify
from app.models.enums import AnalysisStatus, ArticleStatus, IndexStatus
from app.schemas.common import NamedRef, ORMModel, PageParams
from app.schemas.user import UserSummary


def _normalize_tags(tags: list[str]) -> list[str]:
    """Slugify tags (Rejeição 539 -> rejeicao-539), dropping duplicates and keeping order."""
    seen: dict[str, None] = {}
    for tag in tags:
        slug = slugify(tag)
        if slug:
            seen.setdefault(slug, None)
    return list(seen)


Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Tags = Annotated[list[Tag], Field(max_length=20), AfterValidator(_normalize_tags)]
ArticleTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=5, max_length=200)
]
ArticleContent = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=20, max_length=50000)
]


class ArticleCreate(BaseModel):
    title: ArticleTitle
    content: ArticleContent
    category_id: int | None = None
    tags: Tags = Field(default_factory=list)
    status: ArticleStatus = ArticleStatus.DRAFT


class ArticleUpdate(BaseModel):
    title: ArticleTitle | None = None
    content: ArticleContent | None = None
    category_id: int | None = None
    tags: Tags | None = None
    status: ArticleStatus | None = None


class ArticleSummary(ORMModel):
    id: int
    code: str
    title: str
    category: NamedRef | None
    tags: list[str]
    status: ArticleStatus


class ArticleRead(ArticleSummary):
    content: str
    author: UserSummary | None
    index_status: IndexStatus
    index_error: str | None
    indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ArticleFilters(PageParams):
    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(None, description="Text search in title and content.")
    status: ArticleStatus | None = None
    category_id: int | None = None
    tag: str | None = None


class SearchHit(BaseModel):
    article: ArticleSummary
    score: float
    excerpt: str


class ReindexResult(BaseModel):
    articles: int


class SuggestionSourceRead(ORMModel):
    article_id: int | None
    article_code: str
    article_title: str
    rank: int
    score: float
    cited: bool


class SuggestionRead(ORMModel):
    id: int
    status: AnalysisStatus
    provider: str
    model: str
    embedding_model: str | None
    can_answer: bool | None
    answer: str | None
    sources: list[SuggestionSourceRead]
    error_code: str | None
    requested_by: UserSummary | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    created_at: datetime
