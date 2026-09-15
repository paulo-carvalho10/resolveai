"""Text embedders.

`VoyageEmbedder` calls the Voyage AI embeddings API (semantic, multilingual). `HashingEmbedder`
is a free, offline, deterministic stand-in that captures lexical overlap: good enough for tests,
demos and small knowledge bases, but it does not understand synonyms.
"""

import hashlib
import logging
import math
import re
import time
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal, Protocol

import httpx2

from app.core.config import Settings
from app.core.logger import log_event
from app.core.text import normalize
from app.models import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

InputType = Literal["query", "document"]


@dataclass
class EmbeddingBatch:
    vectors: list[list[float]]
    total_tokens: int | None = None


class EmbeddingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Embedder(Protocol):
    provider: str
    model: str

    def embed(self, texts: list[str], input_type: InputType) -> EmbeddingBatch: ...


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(component * component for component in vector))
    return [component / norm for component in vector] if norm else vector


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Both vectors are stored L2-normalized, so the dot product is the cosine."""
    return sum(x * y for x, y in zip(a, b, strict=True))


# --- Local ---------------------------------------------------------------------------------

_STOPWORDS = frozenset(
    [
        "a",
        "ao",
        "aos",
        "as",
        "ate",
        "com",
        "como",
        "da",
        "das",
        "de",
        "do",
        "dos",
        "e",
        "ela",
        "ele",
        "em",
        "entre",
        "essa",
        "esse",
        "esta",
        "este",
        "eu",
        "foi",
        "ha",
        "isso",
        "ja",
        "mais",
        "mas",
        "me",
        "meu",
        "minha",
        "na",
        "nao",
        "nas",
        "no",
        "nos",
        "o",
        "os",
        "ou",
        "para",
        "pela",
        "pelo",
        "por",
        "pra",
        "que",
        "se",
        "sem",
        "ser",
        "so",
        "sua",
        "seu",
        "tem",
        "ter",
        "um",
        "uma",
        "umas",
        "uns",
        "voce",
    ]
)


class HashingEmbedder:
    """Feature hashing of words, word pairs and word prefixes into a fixed-size vector.

    Prefixes ("emiss" from "emissao", "emit" from "emitir") let related word forms share
    features, which is what makes "não consigo emitir" find an article about "emissão".
    """

    provider = "local"
    model = "local-hashing-v1"

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str], input_type: InputType) -> EmbeddingBatch:
        return EmbeddingBatch(vectors=[self._embed_one(text) for text in texts])

    def _embed_one(self, text: str) -> list[float]:
        words = [
            word
            for word in re.findall(r"[a-z0-9]+", normalize(text))
            if len(word) > 1 and word not in _STOPWORDS
        ]
        vector = [0.0] * self.dimensions
        features: list[tuple[str, float]] = [(f"w:{word}", 1.0) for word in words]
        features += [(f"p:{word[:4]}", 0.5) for word in words if len(word) > 4]
        features += [(f"b:{a}_{b}", 0.7) for a, b in pairwise(words)]
        for feature, weight in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign * weight
        return l2_normalize(vector)


# --- Voyage AI -----------------------------------------------------------------------------

VOYAGE_EMBEDDINGS_URL = "https://api.voyageai.com/v1/embeddings"
# The API accepts up to 1,000 inputs per request; smaller batches keep each request quick.
_VOYAGE_BATCH_SIZE = 100
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class VoyageEmbedder:
    provider = "voyage"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        http_client: httpx2.Client | None = None,
    ) -> None:
        self.model = model
        self._max_retries = max_retries
        self._client = http_client or httpx2.Client(timeout=timeout_seconds)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    @classmethod
    def from_settings(cls, settings: Settings) -> "VoyageEmbedder":
        assert settings.voyage_api_key is not None
        return cls(
            api_key=settings.voyage_api_key,
            model=settings.embedding_model,
            timeout_seconds=settings.embedding_timeout_seconds,
        )

    def embed(self, texts: list[str], input_type: InputType) -> EmbeddingBatch:
        vectors: list[list[float]] = []
        total_tokens = 0
        for start in range(0, len(texts), _VOYAGE_BATCH_SIZE):
            batch = texts[start : start + _VOYAGE_BATCH_SIZE]
            payload = self._request(batch, input_type)
            vectors.extend(self._parse_vectors(payload, len(batch)))
            total_tokens += int(payload.get("usage", {}).get("total_tokens") or 0)
        return EmbeddingBatch(vectors=vectors, total_tokens=total_tokens)

    def _request(self, texts: list[str], input_type: InputType) -> dict:
        body = {
            "input": texts,
            "model": self.model,
            "input_type": input_type,
            "output_dimension": EMBEDDING_DIMENSIONS,
        }
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(
                    VOYAGE_EMBEDDINGS_URL, json=body, headers=self._headers
                )
            except httpx2.TimeoutException as exc:
                if attempt < self._max_retries:
                    continue
                raise EmbeddingError("EMBEDDING_TIMEOUT", "Embedding provider timed out.") from exc
            except httpx2.TransportError as exc:
                if attempt < self._max_retries:
                    continue
                raise EmbeddingError(
                    "EMBEDDING_UNAVAILABLE", "Could not reach the embedding provider."
                ) from exc

            if response.status_code in _RETRYABLE_STATUS and attempt < self._max_retries:
                time.sleep(min(2**attempt, 8))
                continue
            if response.status_code in (401, 403):
                raise EmbeddingError("EMBEDDING_AUTH_FAILED", "Invalid Voyage AI API key.")
            if response.status_code == 429:
                raise EmbeddingError(
                    "EMBEDDING_RATE_LIMITED", "Embedding provider rate limit reached."
                )
            if response.status_code >= 400:
                log_event(
                    logger,
                    "embedding.request_failed",
                    level=logging.ERROR,
                    status=response.status_code,
                    body=response.text[:200],
                )
                raise EmbeddingError(
                    "EMBEDDING_PROVIDER_ERROR",
                    f"Embedding provider returned HTTP {response.status_code}.",
                )
            try:
                return response.json()
            except ValueError as exc:
                raise EmbeddingError(
                    "EMBEDDING_INVALID_OUTPUT", "Embedding provider returned invalid JSON."
                ) from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _parse_vectors(payload: dict, expected: int) -> list[list[float]]:
        try:
            items = sorted(payload["data"], key=lambda item: item["index"])
            vectors = [l2_normalize([float(x) for x in item["embedding"]]) for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(
                "EMBEDDING_INVALID_OUTPUT", "Unexpected embedding response."
            ) from exc
        if len(vectors) != expected or any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
            raise EmbeddingError("EMBEDDING_INVALID_OUTPUT", "Unexpected embedding dimensions.")
        return vectors


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "voyage":
        return VoyageEmbedder.from_settings(settings)
    return HashingEmbedder()
