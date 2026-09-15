import json
import math
from collections.abc import Callable

import httpx2
import pytest

from app.core.config import Settings
from app.models import EMBEDDING_DIMENSIONS
from app.services import embeddings
from app.services.embeddings import (
    VOYAGE_EMBEDDINGS_URL,
    EmbeddingError,
    HashingEmbedder,
    VoyageEmbedder,
    build_embedder,
    cosine_similarity,
)

# --- Local hashing embedder ----------------------------------------------------------------


def embed_one(text: str) -> list[float]:
    return HashingEmbedder().embed([text], input_type="document").vectors[0]


def test_hashing_vectors_are_normalized_and_deterministic() -> None:
    vector = embed_one("Rejeição 539 na emissão de NF-e")

    assert len(vector) == EMBEDDING_DIMENSIONS
    assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0)
    assert vector == embed_one("Rejeição 539 na emissão de NF-e")


def test_hashing_ignores_accents_case_and_stopwords() -> None:
    assert embed_one("Emissão da NOTA") == embed_one("emissao nota")


def test_hashing_ranks_related_text_above_unrelated() -> None:
    query = embed_one("não consigo emitir nota fiscal, rejeição de duplicidade")
    related = embed_one("Rejeição 539: duplicidade na emissão de NF-e")
    unrelated = embed_one("A VPN desconecta a cada cinco minutos")

    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated) + 0.1


def test_empty_text_produces_zero_vector_without_error() -> None:
    assert set(embed_one("de da do")) == {0.0}


# --- Voyage embedder -----------------------------------------------------------------------


def voyage_response(count: int, dims: int = EMBEDDING_DIMENSIONS, reverse: bool = False) -> dict:
    data = [
        {"object": "embedding", "embedding": [float(i + 1)] + [0.0] * (dims - 1), "index": i}
        for i in range(count)
    ]
    return {
        "object": "list",
        "data": list(reversed(data)) if reverse else data,
        "model": "voyage-4-lite",
        "usage": {"total_tokens": 7 * count},
    }


def make_voyage(handler: Callable[[httpx2.Request], httpx2.Response]) -> VoyageEmbedder:
    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return VoyageEmbedder(api_key="pa-test", model="voyage-4-lite", http_client=client)


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings.time, "sleep", lambda _: None)


def test_voyage_request_and_response_parsing() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        body = json.loads(request.content)
        return httpx2.Response(200, json=voyage_response(len(body["input"]), reverse=True))

    batch = make_voyage(handler).embed(["primeiro", "segundo"], input_type="query")

    request = requests[0]
    assert str(request.url) == VOYAGE_EMBEDDINGS_URL
    assert request.headers["Authorization"] == "Bearer pa-test"
    assert json.loads(request.content) == {
        "input": ["primeiro", "segundo"],
        "model": "voyage-4-lite",
        "input_type": "query",
        "output_dimension": EMBEDDING_DIMENSIONS,
    }
    # Results are re-ordered by index and normalized.
    assert [vector[0] for vector in batch.vectors] == [1.0, 1.0]
    assert batch.total_tokens == 14


def test_voyage_splits_large_inputs_into_batches() -> None:
    sizes: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        count = len(json.loads(request.content)["input"])
        sizes.append(count)
        return httpx2.Response(200, json=voyage_response(count))

    batch = make_voyage(handler).embed([f"texto {i}" for i in range(250)], input_type="document")

    assert sizes == [100, 100, 50]
    assert len(batch.vectors) == 250


def test_voyage_retries_transient_errors() -> None:
    statuses = iter([429, 503, 200])

    def handler(request: httpx2.Request) -> httpx2.Response:
        status = next(statuses)
        return httpx2.Response(status, json=voyage_response(1) if status == 200 else {})

    assert len(make_voyage(handler).embed(["texto"], "query").vectors) == 1


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (401, {"detail": "unauthorized"}, "EMBEDDING_AUTH_FAILED"),
        (429, {}, "EMBEDDING_RATE_LIMITED"),
        (500, {}, "EMBEDDING_PROVIDER_ERROR"),
        (400, {"detail": "bad model"}, "EMBEDDING_PROVIDER_ERROR"),
        (200, voyage_response(1, dims=512), "EMBEDDING_INVALID_OUTPUT"),
        (200, {"unexpected": True}, "EMBEDDING_INVALID_OUTPUT"),
    ],
)
def test_voyage_errors_are_mapped(status: int, body: dict, code: str) -> None:
    embedder = make_voyage(lambda request: httpx2.Response(status, json=body))

    with pytest.raises(EmbeddingError) as exc_info:
        embedder.embed(["texto"], "query")
    assert exc_info.value.code == code


def test_voyage_timeout_is_mapped() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(EmbeddingError) as exc_info:
        make_voyage(handler).embed(["texto"], "query")
    assert exc_info.value.code == "EMBEDDING_TIMEOUT"


# --- Configuration -------------------------------------------------------------------------


def test_build_embedder_uses_configured_provider() -> None:
    assert isinstance(build_embedder(Settings(_env_file=None)), HashingEmbedder)

    voyage = build_embedder(
        Settings(_env_file=None, embedding_provider="voyage", voyage_api_key="pa-test")
    )
    assert isinstance(voyage, VoyageEmbedder)
    assert voyage.model == "voyage-4-lite"


def test_voyage_requires_api_key_and_scores_are_per_provider() -> None:
    with pytest.raises(ValueError, match="VOYAGE_API_KEY"):
        Settings(_env_file=None, embedding_provider="voyage")

    assert Settings(_env_file=None).effective_rag_min_score == 0.15
    assert Settings(_env_file=None, rag_min_score=0.5).effective_rag_min_score == 0.5


def test_empty_values_in_env_file_mean_default(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """The .env.example ships `RAG_MIN_SCORE=` and `VOYAGE_API_KEY=`; the app must still start."""
    for name in ("RAG_MIN_SCORE", "EMBEDDING_PROVIDER", "AI_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("RAG_MIN_SCORE=\nVOYAGE_API_KEY=\nANTHROPIC_API_KEY=\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.effective_rag_min_score == 0.15
    assert settings.voyage_api_key is None
