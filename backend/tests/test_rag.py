"""RAG suggestions: retrieval over the knowledge base, grounded answers and cited sources."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models import User
from app.services.ai_classifier import TicketText
from app.services.answer_generator import (
    ANSWER_SYSTEM_PROMPT,
    AnswerResult,
    ClaudeAnswerGenerator,
    GeneratedAnswer,
    SourceArticle,
    render_articles,
)
from app.services.claude import AIError
from app.services.embeddings import EmbeddingBatch, EmbeddingError, HashingEmbedder, InputType
from tests.conftest import auth_headers

ARTICLES = [
    {
        "title": "Rejeição 539: duplicidade de NF-e",
        "content": "A rejeição 539 indica que já existe NF-e autorizada com o mesmo número.\n\n"
        "1. Consulte a nota na SEFAZ.\n2. Importe o XML autorizado em vez de emitir de novo.",
        "status": "PUBLISHED",
    },
    {
        "title": "VPN desconectando com frequência",
        "content": "Atualize o cliente VPN e desative a desconexão por inatividade.",
        "status": "PUBLISHED",
    },
    {
        "title": "Rascunho: rejeição 539 em homologação",
        "content": "Texto ainda não revisado sobre rejeição 539 e duplicidade de NF-e.",
        "status": "DRAFT",
    },
]
NFE_TICKET = {
    "title": "Não consigo emitir NF-e",
    "description": "A SEFAZ retorna rejeição 539 de duplicidade ao transmitir a nota.",
}
UNRELATED_TICKET = {
    "title": "Impressora fazendo barulho",
    "description": "A impressora do escritório faz um ruído estranho ao imprimir.",
}


class StubGenerator:
    provider = "stub"
    model = "stub-answer-1"

    def __init__(self) -> None:
        self.outcome: GeneratedAnswer | Exception | None = None
        self.calls: list[tuple[TicketText, list[SourceArticle]]] = []

    def generate(self, ticket: TicketText, articles: list[SourceArticle]) -> AnswerResult:
        self.calls.append((ticket, articles))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        answer = self.outcome or GeneratedAnswer(
            can_answer=bool(articles),
            answer="Importe o XML autorizado." if articles else "Nenhum artigo cobre.",
            sources=[articles[0].code] if articles else [],
        )
        return AnswerResult(answer=answer, provider=self.provider, model=self.model, latency_ms=5)


@pytest.fixture
def articles(client: TestClient, admin: User) -> list[dict[str, Any]]:
    created = []
    for payload in ARTICLES:
        response = client.post("/knowledge", json=payload, headers=auth_headers(admin))
        assert response.status_code == 201
        created.append(response.json())
    return created


@pytest.fixture
def open_ticket(client: TestClient, requester: User) -> Callable[..., dict[str, Any]]:
    def factory(payload: dict[str, str]) -> dict[str, Any]:
        response = client.post("/tickets", json=payload, headers=auth_headers(requester))
        assert response.status_code == 201, response.text
        return response.json()

    return factory


def suggestions(client: TestClient, user: User, ticket_id: int) -> list[dict[str, Any]]:
    response = client.get(f"/tickets/{ticket_id}/ai/suggestions", headers=auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()


# --- Automatic suggestion on ticket creation -----------------------------------------------


def test_ticket_gets_a_grounded_suggestion_with_sources(
    client: TestClient,
    agent: User,
    articles: list[dict[str, Any]],
    open_ticket: Callable[..., dict[str, Any]],
) -> None:
    ticket = open_ticket(NFE_TICKET)

    [suggestion] = suggestions(client, agent, ticket["id"])
    nfe_article = articles[0]
    assert suggestion["status"] == "SUCCEEDED"
    assert (suggestion["provider"], suggestion["embedding_model"]) == (
        "extractive",
        "local-hashing-v1",
    )
    assert suggestion["can_answer"] is True
    assert suggestion["answer"].startswith(f"Artigo mais relevante: {nfe_article['code']}")
    assert "Importe o XML autorizado" in suggestion["answer"]

    top = suggestion["sources"][0]
    assert (top["article_id"], top["article_code"], top["rank"], top["cited"]) == (
        nfe_article["id"],
        nfe_article["code"],
        1,
        True,
    )
    # Drafts are never used as sources.
    assert articles[2]["id"] not in {source["article_id"] for source in suggestion["sources"]}


def test_ticket_without_relevant_articles_says_so(
    client: TestClient,
    agent: User,
    articles: list[dict[str, Any]],
    open_ticket: Callable[..., dict[str, Any]],
) -> None:
    ticket = open_ticket(UNRELATED_TICKET)

    [suggestion] = suggestions(client, agent, ticket["id"])
    assert suggestion["can_answer"] is False
    assert suggestion["sources"] == []
    assert suggestion["answer"] == "Nenhum artigo da base de conhecimento cobre este chamado."


def test_suggestion_on_create_can_be_disabled(
    client: TestClient,
    agent: User,
    open_ticket: Callable[..., dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "ai_suggest_on_create", False)
    ticket = open_ticket(NFE_TICKET)
    assert suggestions(client, agent, ticket["id"]) == []


# --- Grounding rules, with a controllable generator ----------------------------------------


@pytest.fixture
def stub_generator(client: TestClient) -> StubGenerator:
    """Replaces the extractive generator only in the tests that ask for it."""
    from app.api.deps import get_answer_generator
    from app.main import app

    stub = StubGenerator()
    app.dependency_overrides[get_answer_generator] = lambda: stub
    return stub


def test_generator_receives_retrieved_passages_and_ticket(
    client: TestClient,
    articles: list[dict[str, Any]],
    open_ticket: Callable[..., dict[str, Any]],
    stub_generator: StubGenerator,
) -> None:
    open_ticket(NFE_TICKET)

    ticket_text, sources = stub_generator.calls[0]
    assert ticket_text.title == NFE_TICKET["title"]
    assert sources[0].code == articles[0]["code"]
    assert "Importe o XML autorizado" in sources[0].passages[0]


def test_citations_of_articles_that_were_not_retrieved_are_discarded(
    client: TestClient,
    agent: User,
    articles: list[dict[str, Any]],
    open_ticket: Callable[..., dict[str, Any]],
    stub_generator: StubGenerator,
) -> None:
    stub_generator.outcome = GeneratedAnswer(
        can_answer=True,
        answer="Resposta.",
        sources=[articles[0]["code"], "KB-999", articles[2]["code"]],
    )

    ticket = open_ticket(NFE_TICKET)

    [suggestion] = suggestions(client, agent, ticket["id"])
    cited = [source["article_code"] for source in suggestion["sources"] if source["cited"]]
    assert cited == [articles[0]["code"]]


def test_can_answer_is_false_when_nothing_was_retrieved(
    client: TestClient,
    agent: User,
    open_ticket: Callable[..., dict[str, Any]],
    stub_generator: StubGenerator,
) -> None:
    stub_generator.outcome = GeneratedAnswer(can_answer=True, answer="Inventado.", sources=[])

    ticket = open_ticket(NFE_TICKET)

    assert suggestions(client, agent, ticket["id"])[0]["can_answer"] is False


def test_generator_failure_is_recorded_without_breaking_ticket_creation(
    client: TestClient,
    agent: User,
    articles: list[dict[str, Any]],
    open_ticket: Callable[..., dict[str, Any]],
    stub_generator: StubGenerator,
) -> None:
    stub_generator.outcome = AIError("AI_RATE_LIMITED", "slow down")

    ticket = open_ticket(NFE_TICKET)

    [suggestion] = suggestions(client, agent, ticket["id"])
    assert (suggestion["status"], suggestion["error_code"]) == ("FAILED", "AI_RATE_LIMITED")


class BrokenEmbedder(HashingEmbedder):
    def embed(self, texts: list[str], input_type: InputType) -> EmbeddingBatch:
        if input_type == "query":
            raise EmbeddingError("EMBEDDING_UNAVAILABLE", "down")
        return super().embed(texts, input_type)


def test_embedding_failure_is_recorded(
    client: TestClient,
    agent: User,
    articles: list[dict[str, Any]],
    open_ticket: Callable[..., dict[str, Any]],
) -> None:
    from app.api.deps import get_embedder
    from app.main import app

    app.dependency_overrides[get_embedder] = lambda: BrokenEmbedder()
    ticket = open_ticket(NFE_TICKET)

    [suggestion] = suggestions(client, agent, ticket["id"])
    assert (suggestion["status"], suggestion["error_code"]) == ("FAILED", "EMBEDDING_UNAVAILABLE")


# --- Manual suggestion ---------------------------------------------------------------------


def test_agent_requests_a_new_suggestion(
    client: TestClient,
    agent: User,
    articles: list[dict[str, Any]],
    open_ticket: Callable[..., dict[str, Any]],
) -> None:
    ticket = open_ticket(NFE_TICKET)

    response = client.post(f"/tickets/{ticket['id']}/ai/suggest", headers=auth_headers(agent))

    assert response.status_code == 200
    assert response.json()["requested_by"]["id"] == agent.id
    assert response.json()["sources"][0]["cited"] is True
    listed = suggestions(client, agent, ticket["id"])
    assert [s["id"] for s in listed] == [response.json()["id"], listed[1]["id"]]


def test_manual_suggestion_errors_and_permissions(
    client: TestClient,
    agent: User,
    requester: User,
    articles: list[dict[str, Any]],
    open_ticket: Callable[..., dict[str, Any]],
    stub_generator: StubGenerator,
) -> None:
    ticket = open_ticket(NFE_TICKET)
    url = f"/tickets/{ticket['id']}/ai/suggest"

    assert client.post(url, headers=auth_headers(requester)).status_code == 403
    assert (
        client.get(
            f"/tickets/{ticket['id']}/ai/suggestions", headers=auth_headers(requester)
        ).status_code
        == 403
    )

    stub_generator.outcome = AIError("AI_TIMEOUT", "timeout")
    failed = client.post(url, headers=auth_headers(agent))
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "AI_TIMEOUT"

    client.patch(f"/tickets/{ticket['id']}", json={"status": "CLOSED"}, headers=auth_headers(agent))
    assert client.post(url, headers=auth_headers(agent)).json()["error"]["code"] == "TICKET_CLOSED"


def test_sources_survive_article_deletion(
    client: TestClient,
    admin: User,
    agent: User,
    articles: list[dict[str, Any]],
    open_ticket: Callable[..., dict[str, Any]],
) -> None:
    ticket = open_ticket(NFE_TICKET)
    client.delete(f"/knowledge/{articles[0]['id']}", headers=auth_headers(admin))

    source = suggestions(client, agent, ticket["id"])[0]["sources"][0]
    assert source["article_id"] is None
    assert source["article_code"] == articles[0]["code"]
    assert source["article_title"] == articles[0]["title"]


# --- Claude answer generator ---------------------------------------------------------------


def test_claude_answer_generator_request() -> None:
    calls: list[dict[str, Any]] = []
    answer = GeneratedAnswer(can_answer=True, answer="Importe o XML.", sources=["KB-001"])

    def parse(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn",
            parsed_output=answer,
            model="claude-haiku-4-5-20251001",
            _request_id="req_test",
            usage=SimpleNamespace(input_tokens=800, output_tokens=150, cache_read_input_tokens=0),
        )

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    generator = ClaudeAnswerGenerator(client, model="claude-haiku-4-5", effort="low")  # type: ignore[arg-type]
    sources = [SourceArticle("KB-001", "Rejeição 539", ("Importe o XML autorizado.",))]

    result = generator.generate(TicketText("Rejeição 539", "Não consigo emitir."), sources)

    assert result.answer == answer
    assert (result.model, result.input_tokens, result.output_tokens) == (
        "claude-haiku-4-5-20251001",
        800,
        150,
    )
    request = calls[0]
    assert request["output_format"] is GeneratedAnswer
    assert request["system"] == [{"type": "text", "text": ANSWER_SYSTEM_PROMPT}]
    assert "output_config" not in request  # Haiku 4.5 does not accept effort
    content = request["messages"][0]["content"]
    assert content.startswith(render_articles(sources))
    assert '<article code="KB-001" title="Rejeição 539">' in content
    assert "<title>Rejeição 539</title>" in content
