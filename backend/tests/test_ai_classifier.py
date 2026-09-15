from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from app.core.config import Settings
from app.services.ai_classifier import (
    SYSTEM_PROMPT,
    Catalog,
    CatalogCategory,
    CatalogTeam,
    Classification,
    ClaudeClassifier,
    KeywordClassifier,
    TicketText,
    build_classifier,
    render_catalog,
)
from app.services.claude import REFUSAL_FALLBACK_BETA, AIError, build_request_options

CATALOG = Catalog(
    categories=(
        CatalogCategory("Infraestrutura", "Rede e servidores", ("VPN", "Servidores")),
        CatalogCategory("Fiscal", "Documentos fiscais", ("NFS-e", "NF-e")),
    ),
    teams=(CatalogTeam("Infraestrutura TI"), CatalogTeam("ERP Fiscal", "Notas fiscais")),
)
TICKET = TicketText("Não consigo emitir NF-e", "Rejeição 539 ao transmitir. Preciso faturar hoje.")

CLASSIFICATION = Classification(
    category="Fiscal",
    subcategory="NF-e",
    team="ERP Fiscal",
    priority="HIGH",
    urgency="HIGH",
    summary="Cliente não consegue emitir NF-e por rejeição 539.",
    reasoning="Emissão de nota bloqueada com prazo hoje.",
    confidence=0.94,
)


# --- Prompt rendering ----------------------------------------------------------------------


def test_catalog_rendering_is_sorted_and_deterministic() -> None:
    shuffled = Catalog(categories=tuple(reversed(CATALOG.categories)), teams=CATALOG.teams[::-1])

    rendered = render_catalog(CATALOG)

    assert rendered == render_catalog(shuffled)
    assert rendered.splitlines() == [
        "<catalog>",
        "Categories:",
        "- Fiscal: Documentos fiscais",
        "  - NF-e",
        "  - NFS-e",
        "- Infraestrutura: Rede e servidores",
        "  - Servidores",
        "  - VPN",
        "Teams:",
        "- ERP Fiscal: Notas fiscais",
        "- Infraestrutura TI",
        "</catalog>",
    ]


# --- Keyword classifier --------------------------------------------------------------------


def test_keyword_classifier_prefers_subcategory_match() -> None:
    result = KeywordClassifier().classify(TICKET, CATALOG)

    assert result.classification.category == "Fiscal"
    assert result.classification.subcategory == "NF-e"
    assert result.classification.priority == "HIGH"
    assert result.classification.confidence == 0.85
    assert result.provider == "keyword"


@pytest.mark.parametrize(
    ("title", "description", "category", "priority", "confidence"),
    [
        (
            "Sistema FORA DO AR",
            "Ninguém consegue acessar os servidores.",
            "Infraestrutura",
            "CRITICAL",
            0.85,
        ),
        (
            "Dúvida sobre relatório",
            "Como faço para exportar a infraestrutura?",
            "Infraestrutura",
            "LOW",
            0.7,
        ),
        ("Impressora com barulho", "Faz um ruído estranho ao imprimir.", None, "MEDIUM", 0.3),
    ],
)
def test_keyword_classifier_signals(
    title: str, description: str, category: str | None, priority: str, confidence: float
) -> None:
    result = KeywordClassifier().classify(TicketText(title, description), CATALOG)

    assert result.classification.category == category
    assert result.classification.priority == priority
    assert result.classification.confidence == confidence


def test_keyword_classifier_matches_whole_words_only() -> None:
    ticket = TicketText("Problema na VPNX", "O cliente VPNX-2 não sincroniza.")
    assert KeywordClassifier().classify(ticket, CATALOG).classification.subcategory is None


# --- Claude classifier ---------------------------------------------------------------------


class FakeMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def fake_client(messages: FakeMessages) -> Any:
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def parsed_response(
    parsed: Classification | None = CLASSIFICATION, stop_reason: str = "end_turn"
) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=parsed,
        model="claude-opus-5",
        _request_id="req_test",
        usage=SimpleNamespace(input_tokens=1200, output_tokens=180, cache_read_input_tokens=900),
    )


def test_claude_classifier_sends_structured_cached_request() -> None:
    messages = FakeMessages(parsed_response())
    classifier = ClaudeClassifier(fake_client(messages), model="claude-opus-5", effort="low")

    result = classifier.classify(TICKET, CATALOG)

    assert result.classification == CLASSIFICATION
    assert (result.provider, result.model) == ("claude", "claude-opus-5")
    assert (result.input_tokens, result.output_tokens) == (1200, 180)

    request = messages.calls[0]
    assert request["model"] == "claude-opus-5"
    assert request["output_format"] is Classification
    assert request["output_config"] == {"effort": "low"}
    assert request["fallbacks"] == "default"
    assert request["betas"] == [REFUSAL_FALLBACK_BETA]
    # Stable instructions first, then the per-organization catalog as the cache breakpoint.
    system = request["system"]
    assert system[0] == {"type": "text", "text": SYSTEM_PROMPT}
    assert system[1]["text"] == render_catalog(CATALOG)
    assert system[1]["cache_control"] == {"type": "ephemeral"}
    # The ticket is the only volatile part and goes last.
    user_content = request["messages"][0]["content"]
    assert "<title>Não consigo emitir NF-e</title>" in user_content
    assert "Rejeição 539" in user_content


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (parsed_response(stop_reason="refusal"), "AI_REFUSED"),
        (parsed_response(stop_reason="max_tokens"), "AI_INCOMPLETE"),
        (parsed_response(parsed=None), "AI_INVALID_OUTPUT"),
    ],
)
def test_claude_classifier_rejects_unusable_responses(response: Any, code: str) -> None:
    classifier = ClaudeClassifier(fake_client(FakeMessages(response)), "claude-opus-5", "low")

    with pytest.raises(AIError) as exc_info:
        classifier.classify(TICKET, CATALOG)
    assert exc_info.value.code == code


_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    return cls("error", response=httpx2.Response(status, request=_REQUEST), body=None)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (_status_error(anthropic.AuthenticationError, 401), "AI_AUTH_FAILED"),
        (_status_error(anthropic.RateLimitError, 429), "AI_RATE_LIMITED"),
        (_status_error(anthropic.InternalServerError, 500), "AI_PROVIDER_ERROR"),
        (anthropic.APITimeoutError(request=_REQUEST), "AI_TIMEOUT"),
        (anthropic.APIConnectionError(request=_REQUEST), "AI_UNAVAILABLE"),
        (ValueError("not json"), "AI_INVALID_OUTPUT"),
    ],
)
def test_claude_classifier_maps_sdk_errors(error: Exception, code: str) -> None:
    classifier = ClaudeClassifier(fake_client(FakeMessages(error=error)), "claude-opus-5", "low")

    with pytest.raises(AIError) as exc_info:
        classifier.classify(TICKET, CATALOG)
    assert exc_info.value.code == code


def test_haiku_request_omits_options_it_does_not_support() -> None:
    messages = FakeMessages(parsed_response())
    classifier = ClaudeClassifier(fake_client(messages), model="claude-haiku-4-5", effort="low")

    classifier.classify(TICKET, CATALOG)

    request = messages.calls[0]
    assert request["model"] == "claude-haiku-4-5"
    assert request["output_format"] is Classification
    assert request["system"][1]["cache_control"] == {"type": "ephemeral"}
    for option in ("output_config", "fallbacks", "betas"):
        assert option not in request


@pytest.mark.parametrize(
    ("model", "has_effort", "has_fallbacks"),
    [
        ("claude-haiku-4-5", False, False),
        ("claude-sonnet-5", True, False),
        ("claude-opus-4-8", True, False),
        ("claude-opus-5", True, True),
        ("claude-fable-5-1", True, True),
        ("some-future-model", False, False),
    ],
)
def test_request_options_depend_on_model(model: str, has_effort: bool, has_fallbacks: bool) -> None:
    options = build_request_options(model, "medium")

    assert ("output_config" in options) is has_effort
    assert ("fallbacks" in options) is has_fallbacks
    if has_effort:
        assert options["output_config"] == {"effort": "medium"}
    if has_fallbacks:
        assert options["betas"] == [REFUSAL_FALLBACK_BETA]


# --- Configuration -------------------------------------------------------------------------


def test_build_classifier_uses_configured_provider() -> None:
    keyword = build_classifier(Settings(_env_file=None, ai_provider="keyword"))
    assert isinstance(keyword, KeywordClassifier)

    claude = build_classifier(
        Settings(_env_file=None, ai_provider="claude", anthropic_api_key="sk-ant-test")
    )
    assert isinstance(claude, ClaudeClassifier)
    assert claude.model == "claude-haiku-4-5"  # cheapest model is the default


def test_claude_provider_requires_api_key() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        Settings(_env_file=None, ai_provider="claude", anthropic_api_key=None)
