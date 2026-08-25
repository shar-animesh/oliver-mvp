"""Single configured model-provider client and structured-response adapter."""

import json
import logging
import time
from functools import lru_cache
from typing import Any, Callable, TypeVar

from openai import APIStatusError, OpenAI
from pydantic import BaseModel, ValidationError

from config import get_settings

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)
ProviderResult = TypeVar("ProviderResult")
logger = logging.getLogger(__name__)

_TRANSIENT_PROVIDER_STATUSES = frozenset({429, 500, 502, 503, 504})


class StructuredOutputError(RuntimeError):
    """A provider response contained no object satisfying the requested schema."""

    def __init__(self, model_name: str, *, candidate_count: int, issues: tuple[str, ...]) -> None:
        self.model_name = model_name
        self.candidate_count = candidate_count
        self.issues = issues
        issue_summary = ", ".join(issues) if issues else "no JSON object found"
        super().__init__(f"No valid {model_name} object ({candidate_count} candidates; {issue_summary})")


@lru_cache(maxsize=1)
def get_model_client() -> OpenAI:
    """Return the process-wide OpenAI-compatible provider client."""
    settings = get_settings()
    return OpenAI(
        api_key=settings.OPENAI_API_KEY.get_secret_value(),
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )


def call_with_bounded_provider_retry(
    operation: Callable[[float], ProviderResult],
    *,
    timeout_seconds: float,
    max_retries: int,
    retryable_result_errors: tuple[type[Exception], ...] = (),
) -> ProviderResult:
    """Retry a bounded provider attempt for explicitly approved failure classes.

    SDK-level retries remain disabled. This boundary shares one attempt counter and
    one total deadline between transient HTTP statuses and caller-approved response
    contract errors, preventing nested or unbounded retries.
    """
    started_at = time.monotonic()
    retry_count = 0
    last_retryable_error: Exception | None = None
    while True:
        remaining_seconds = timeout_seconds - (time.monotonic() - started_at)
        if remaining_seconds <= 0:
            if last_retryable_error is not None:
                raise last_retryable_error
            raise TimeoutError("Model-provider request budget was exhausted")
        try:
            return operation(remaining_seconds)
        except Exception as error:
            transient_status = isinstance(error, APIStatusError) and error.status_code in _TRANSIENT_PROVIDER_STATUSES
            invalid_result = isinstance(error, retryable_result_errors)
            if (not transient_status and not invalid_result) or retry_count >= max_retries:
                raise
            last_retryable_error = error
            retry_count += 1
            backoff_seconds = min(2 ** (retry_count - 1), 8.0, max(0.0, remaining_seconds - 0.1))
            logger.warning(
                "Retrying model-provider request after %s",
                "transient HTTP status" if transient_status else type(error).__name__,
                extra={
                    "provider_status": error.status_code if isinstance(error, APIStatusError) else None,
                    "provider_retry": retry_count,
                },
            )
            if backoff_seconds > 0:
                time.sleep(backoff_seconds)


def call_with_transient_status_retry(
    operation: Callable[[float], ProviderResult],
    *,
    timeout_seconds: float,
    max_retries: int,
) -> ProviderResult:
    """Compatibility wrapper for callers that retry only transient statuses."""
    return call_with_bounded_provider_retry(
        operation,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


def _strict_json_schema(value: Any) -> Any:
    """Apply the JSON-schema restrictions required by Responses structured output."""
    if isinstance(value, list):
        return [_strict_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    strict = {key: _strict_json_schema(item) for key, item in value.items() if key != "default"}
    properties = strict.get("properties")
    if isinstance(properties, dict):
        strict["additionalProperties"] = False
        strict["required"] = list(properties)
    return strict


def structured_text_config(model: type[BaseModel]) -> dict[str, object]:
    """Return a Responses JSON-schema format accepted by OpenAI-compatible providers."""
    return {
        "format": {
            "type": "json_schema",
            "name": model.__name__[:64],
            "schema": _strict_json_schema(model.model_json_schema()),
            "strict": True,
        }
    }


def _json_objects(value: str) -> list[str]:
    """Extract complete JSON objects without treating surrounding prose as data."""
    decoder = json.JSONDecoder()
    objects: list[str] = []
    position = 0
    while (start := value.find("{", position)) >= 0:
        try:
            _, length = decoder.raw_decode(value[start:])
        except json.JSONDecodeError:
            position = start + 1
            continue
        objects.append(value[start : start + length])
        position = start + length
    return objects


def _response_diagnostics(response: Any) -> list[str]:
    """Describe an incomplete provider response without recording its content."""
    diagnostics: list[str] = []
    status = getattr(response, "status", None)
    if status:
        diagnostics.append(f"response_status:{status}")
    incomplete_details = getattr(response, "incomplete_details", None)
    reason = getattr(incomplete_details, "reason", None)
    if reason:
        diagnostics.append(f"incomplete_reason:{reason}")
    content_types = {
        str(content_type)
        for item in getattr(response, "output", ()) or ()
        for content in getattr(item, "content", ()) or ()
        if (content_type := getattr(content, "type", None))
    }
    if content_types:
        diagnostics.append(f"content_types:{'|'.join(sorted(content_types))}")
    return diagnostics


def parse_structured_output(response: Any, model: type[StructuredModel]) -> StructuredModel:
    """Validate the last schema-shaped message from a Responses result.

    Some OpenAI-compatible gateways return a harmless assistant preamble as a
    separate message before the schema-constrained JSON. The SDK parser fails on
    that first message. This adapter ignores non-JSON messages but never repairs,
    coerces, or partially accepts an invalid structured object.
    """
    candidates: list[str] = []
    for item in reversed(response.output):
        for content in reversed(getattr(item, "content", ()) or ()):
            text = getattr(content, "text", None)
            if isinstance(text, str):
                candidates.extend(reversed(_json_objects(text)))
    issues: list[str] = []
    for candidate in candidates:
        try:
            return model.model_validate_json(candidate)
        except ValidationError as error:
            for issue in error.errors(include_input=False)[:12]:
                location = ".".join(str(part) for part in issue["loc"]) or "root"
                issues.append(f"{location}:{issue['type']}")
            continue
    issues.extend(_response_diagnostics(response))
    raise StructuredOutputError(
        model.__name__,
        candidate_count=len(candidates),
        issues=tuple(dict.fromkeys(issues)),
    )
