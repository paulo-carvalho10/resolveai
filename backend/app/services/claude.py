"""Shared Claude call: structured output, per-model options and uniform error handling.

Both the ticket classifier and the RAG answer generator go through `call_structured`, so
model-specific quirks and SDK error mapping live in one place.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

import anthropic
from pydantic import BaseModel

from app.core.config import Settings
from app.core.logger import log_event

logger = logging.getLogger(__name__)

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Request options are model-specific: sending one a model does not support returns HTTP 400
# and would fail every call. Unknown models get neither option.
# `output_config.effort`: rejected by Haiku 4.5 and older models.
_EFFORT_MODEL_PREFIXES = (
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-fable-",
    "claude-mythos-",
)
# Server-side refusal fallbacks: for the models whose safety classifiers can decline requests.
_REFUSAL_FALLBACK_MODEL_PREFIXES = ("claude-opus-5", "claude-fable-", "claude-mythos-")


class AIError(Exception):
    """A provider failure translated to one of our error codes (AI_TIMEOUT, AI_REFUSED...)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class StructuredResult[T: BaseModel]:
    output: T
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int


def build_client(settings: Settings) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.ai_timeout_seconds,
        max_retries=settings.ai_max_retries,
    )


def build_request_options(model: str, effort: str) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if model.startswith(_EFFORT_MODEL_PREFIXES):
        options["output_config"] = {"effort": effort}
    if model.startswith(_REFUSAL_FALLBACK_MODEL_PREFIXES):
        # Re-run on Anthropic's recommended fallback model instead of failing.
        options["betas"] = [REFUSAL_FALLBACK_BETA]
        options["fallbacks"] = "default"
    return options


def call_structured[T: BaseModel](
    client: anthropic.Anthropic,
    *,
    model: str,
    effort: str,
    system: list[dict[str, Any]],
    user_content: str,
    output_format: type[T],
    max_tokens: int,
    event: str,
) -> StructuredResult[T]:
    start = time.perf_counter()
    try:
        response = client.beta.messages.parse(
            model=model,
            max_tokens=max_tokens,
            **build_request_options(model, effort),
            system=system,
            messages=[{"role": "user", "content": user_content}],
            output_format=output_format,
        )
    except anthropic.AuthenticationError as exc:
        raise AIError("AI_AUTH_FAILED", "Invalid Anthropic API key.") from exc
    except anthropic.RateLimitError as exc:
        raise AIError("AI_RATE_LIMITED", "AI provider rate limit reached.") from exc
    except anthropic.APITimeoutError as exc:
        raise AIError("AI_TIMEOUT", "AI provider timed out.") from exc
    except anthropic.APIConnectionError as exc:
        raise AIError("AI_UNAVAILABLE", "Could not reach the AI provider.") from exc
    except anthropic.APIStatusError as exc:
        raise AIError("AI_PROVIDER_ERROR", f"AI provider returned HTTP {exc.status_code}.") from exc
    except ValueError as exc:  # pydantic.ValidationError and JSON decode errors
        raise AIError("AI_INVALID_OUTPUT", "AI returned an invalid result.") from exc

    latency_ms = round((time.perf_counter() - start) * 1000)
    if response.stop_reason == "refusal":
        raise AIError("AI_REFUSED", "The AI declined this request.")
    if response.stop_reason == "max_tokens":
        raise AIError("AI_INCOMPLETE", "AI response was cut off.")
    output = response.parsed_output
    if output is None:
        raise AIError("AI_INVALID_OUTPUT", "AI returned an invalid result.")

    usage = response.usage
    log_event(
        logger,
        event,
        model=response.model,
        request_id=response._request_id,
        input_tokens=usage.input_tokens,
        cache_read_tokens=usage.cache_read_input_tokens,
        output_tokens=usage.output_tokens,
        latency_ms=latency_ms,
    )
    return StructuredResult(
        output=output,
        # The fallback model may have served the request.
        model=response.model,
        latency_ms=latency_ms,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
