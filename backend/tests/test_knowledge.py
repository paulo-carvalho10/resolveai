from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, User
from app.services.embeddings import EmbeddingBatch, EmbeddingError, HashingEmbedder, InputType
from app.services.knowledge_service import chunk_text
from tests.conftest import auth_headers

REJECTION_539 = {
    "title": "Rejeição 539: duplicidade de NF-e",
    "content": "A rejeição 539 ocorre quando já existe NF-e autorizada com o mesmo número.\n\n"
    "1. Consulte a nota na SEFAZ.\n2. Importe o XML autorizado em vez de emitir de novo.",
    "tags": ["NF-e", "Rejeição 539", "nfe"],
    "status": "PUBLISHED",
}
VPN = {
    "title": "VPN desconectando com frequência",
    "content": "Atualize o cliente VPN e desative a desconexão por inatividade nas configurações.",
    "tags": ["vpn", "rede"],
    "status": "PUBLISHED",
}


class FailingEmbedder(HashingEmbedder):
    def embed(self, texts: list[str], input_type: InputType) -> EmbeddingBatch:
        raise EmbeddingError("EMBEDDING_RATE_LIMITED", "slow down")


@pytest.fixture
def create_article(client: TestClient, admin: User) -> Callable[..., dict[str, Any]]:
    def factory(**payload: Any) -> dict[str, Any]:
        response = client.post("/knowledge", json=payload, headers=auth_headers(admin))
        assert response.status_code == 201, response.text
        # Indexing ran as a background task; read the article again to see its final state.
        return client.get(f"/knowledge/{response.json()['id']}", headers=auth_headers(admin)).json()

    return factory


def chunk_count(db: Session, article_id: int) -> int:
    stmt = select(func.count()).where(KnowledgeChunk.article_id == article_id)
    return db.scalar(stmt) or 0


# --- Chunking ------------------------------------------------------------------------------


def test_short_content_is_one_chunk() -> None:
    assert chunk_text("Primeiro parágrafo.\n\nSegundo parágrafo.") == [
        "Primeiro parágrafo.\n\nSegundo parágrafo."
    ]


def test_paragraphs_are_grouped_up_to_the_limit() -> None:
    paragraphs = [f"Parágrafo {i}: " + "texto " * 30 for i in range(6)]

    chunks = chunk_text("\n\n".join(paragraphs), max_chars=500, overlap=50)

    assert len(chunks) > 1
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert "\n\n".join(chunks).count("Parágrafo") == 6  # nothing lost, nothing duplicated


def test_long_paragraph_is_split_with_overlap() -> None:
    words = [f"palavra{i}" for i in range(200)]

    chunks = chunk_text(" ".join(words), max_chars=300, overlap=60)

    assert all(len(chunk) <= 300 for chunk in chunks)
    assert chunks[0].split()[-1] in chunks[1]  # boundary text repeated in the next chunk
    assert set(words) <= set(" ".join(chunks).split())


# --- Articles ------------------------------------------------------------------------------


def test_admin_creates_article_and_it_gets_indexed(
    create_article: Callable[..., dict[str, Any]], db: Session
) -> None:
    article = create_article(**REJECTION_539)

    assert article["code"] == f"KB-{article['id']:03d}"
    assert article["tags"] == ["nf-e", "rejeicao-539", "nfe"]
    assert article["index_status"] == "INDEXED"
    assert article["indexed_at"] is not None
    assert article["author"]["full_name"] == "Ana Admin"
    assert chunk_count(db, article["id"]) == 1


def test_only_admins_write_articles(client: TestClient, agent: User, requester: User) -> None:
    for user in (agent, requester):
        response = client.post("/knowledge", json=REJECTION_539, headers=auth_headers(user))
        assert response.status_code == 403


def test_requesters_only_see_published_articles(
    client: TestClient,
    requester: User,
    agent: User,
    create_article: Callable[..., dict[str, Any]],
) -> None:
    published = create_article(**REJECTION_539)
    draft = create_article(**{**VPN, "status": "DRAFT"})

    requester_list = client.get("/knowledge", headers=auth_headers(requester)).json()
    assert [a["id"] for a in requester_list["items"]] == [published["id"]]
    assert (
        client.get(f"/knowledge/{draft['id']}", headers=auth_headers(requester)).status_code == 404
    )

    agent_list = client.get("/knowledge", headers=auth_headers(agent)).json()
    assert agent_list["total"] == 2


def test_articles_are_isolated_between_organizations(
    client: TestClient, other_admin: User, create_article: Callable[..., dict[str, Any]]
) -> None:
    article = create_article(**REJECTION_539)

    response = client.get(f"/knowledge/{article['id']}", headers=auth_headers(other_admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ARTICLE_NOT_FOUND"
    assert client.get("/knowledge", headers=auth_headers(other_admin)).json()["total"] == 0


def test_list_filters(
    client: TestClient,
    admin: User,
    agent: User,
    create_article: Callable[..., dict[str, Any]],
) -> None:
    category = client.post(
        "/categories", json={"name": "Fiscal"}, headers=auth_headers(admin)
    ).json()
    nfe = create_article(**REJECTION_539, category_id=category["id"])
    vpn = create_article(**{**VPN, "status": "DRAFT"})

    def ids(**params: object) -> list[int]:
        response = client.get("/knowledge", params=params, headers=auth_headers(agent))
        assert response.status_code == 200, response.text
        return [a["id"] for a in response.json()["items"]]

    assert ids(q="inatividade") == [vpn["id"]]
    assert ids(tag="Rejeição 539") == [nfe["id"]]
    assert ids(tag="rejeicao") == []  # exact tag, not a substring
    assert ids(status="DRAFT") == [vpn["id"]]
    assert ids(category_id=category["id"]) == [nfe["id"]]


def test_category_must_belong_to_organization(
    client: TestClient, admin: User, other_admin: User
) -> None:
    foreign = client.post("/categories", json={"name": "Globex"}, headers=auth_headers(other_admin))
    response = client.post(
        "/knowledge",
        json={**REJECTION_539, "category_id": foreign.json()["id"]},
        headers=auth_headers(admin),
    )
    assert response.status_code == 404


def test_editing_text_reindexes_but_editing_tags_does_not(
    client: TestClient,
    admin: User,
    db: Session,
    create_article: Callable[..., dict[str, Any]],
) -> None:
    article = create_article(**REJECTION_539)
    url = f"/knowledge/{article['id']}"

    client.patch(url, json={"tags": ["fiscal"]}, headers=auth_headers(admin))
    after_tags = client.get(url, headers=auth_headers(admin)).json()
    assert after_tags["indexed_at"] == article["indexed_at"]

    new_content = "Conteúdo revisado sobre a rejeição 539.\n\n" + "Passo detalhado. " * 120
    client.patch(url, json={"content": new_content}, headers=auth_headers(admin))
    after_content = client.get(url, headers=auth_headers(admin)).json()
    assert after_content["indexed_at"] != article["indexed_at"]
    assert chunk_count(db, article["id"]) > 1  # the longer text was re-chunked


def test_indexing_failure_is_recorded(
    client: TestClient, admin: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.deps import get_embedder
    from app.main import app

    app.dependency_overrides[get_embedder] = lambda: FailingEmbedder()
    response = client.post("/knowledge", json=REJECTION_539, headers=auth_headers(admin))
    article = client.get(f"/knowledge/{response.json()['id']}", headers=auth_headers(admin)).json()

    assert article["index_status"] == "FAILED"
    assert article["index_error"] == "EMBEDDING_RATE_LIMITED"


def test_delete_article_removes_chunks(
    client: TestClient,
    admin: User,
    db: Session,
    create_article: Callable[..., dict[str, Any]],
) -> None:
    article = create_article(**REJECTION_539)

    assert (
        client.delete(f"/knowledge/{article['id']}", headers=auth_headers(admin)).status_code == 204
    )
    assert chunk_count(db, article["id"]) == 0


# --- Search --------------------------------------------------------------------------------


def test_semantic_search_ranks_relevant_published_articles(
    client: TestClient,
    requester: User,
    other_admin: User,
    create_article: Callable[..., dict[str, Any]],
) -> None:
    nfe = create_article(**REJECTION_539)
    create_article(**VPN)
    create_article(**{**REJECTION_539, "title": "Rascunho sobre rejeição 539", "status": "DRAFT"})
    client.post(
        "/knowledge",
        json={**REJECTION_539, "title": "Artigo de outra empresa"},
        headers=auth_headers(other_admin),
    )

    hits = client.get(
        "/knowledge/search",
        params={"q": "não consigo emitir, deu rejeição 539 de duplicidade"},
        headers=auth_headers(requester),
    ).json()

    assert [hit["article"]["id"] for hit in hits] == [nfe["id"]]
    assert hits[0]["article"]["code"] == nfe["code"]
    assert hits[0]["score"] > 0.15
    assert "rejeição 539" in hits[0]["excerpt"]


def test_search_with_no_relevant_article_returns_empty(
    client: TestClient, agent: User, create_article: Callable[..., dict[str, Any]]
) -> None:
    create_article(**REJECTION_539)

    response = client.get(
        "/knowledge/search", params={"q": "impressora fazendo barulho"}, headers=auth_headers(agent)
    )
    assert response.json() == []


def test_search_failure_returns_502(client: TestClient, agent: User) -> None:
    from app.api.deps import get_embedder
    from app.main import app

    app.dependency_overrides[get_embedder] = lambda: FailingEmbedder()
    response = client.get(
        "/knowledge/search", params={"q": "rejeição"}, headers=auth_headers(agent)
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EMBEDDING_RATE_LIMITED"


class OtherModelEmbedder(HashingEmbedder):
    model = "local-hashing-v2"


def test_reindex_moves_articles_to_the_current_embedding_model(
    client: TestClient,
    admin: User,
    agent: User,
    db: Session,
    create_article: Callable[..., dict[str, Any]],
) -> None:
    from app.api.deps import get_embedder
    from app.main import app

    create_article(**REJECTION_539)
    app.dependency_overrides[get_embedder] = lambda: OtherModelEmbedder()
    query = {"q": "rejeição 539 duplicidade"}

    # Vectors from another model are never compared with the new model's queries.
    assert client.get("/knowledge/search", params=query, headers=auth_headers(agent)).json() == []

    assert client.post("/knowledge/reindex", headers=auth_headers(agent)).status_code == 403
    response = client.post("/knowledge/reindex", headers=auth_headers(admin))
    assert response.status_code == 202
    assert response.json() == {"articles": 1}

    assert (
        len(client.get("/knowledge/search", params=query, headers=auth_headers(agent)).json()) == 1
    )
    models = set(db.scalars(select(KnowledgeChunk.embedding_model)))
    assert models == {"local-hashing-v2"}
