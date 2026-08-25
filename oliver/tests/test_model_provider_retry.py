"""Bounded model-provider retry policy tests."""

import httpx
import pytest
from openai import APIStatusError

from utils.model_provider import StructuredOutputError, call_with_bounded_provider_retry


@pytest.fixture(autouse=True)
def disable_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep retry-policy tests fast while production retains bounded backoff."""
    monkeypatch.setattr("utils.model_provider.time.sleep", lambda _seconds: None)


def _status_error(status_code: int) -> APIStatusError:
    request = httpx.Request("POST", "https://provider.invalid/v1/responses")
    response = httpx.Response(status_code, request=request)
    return APIStatusError("provider status", response=response, body={"error": {"type": "test"}})


def test_retries_one_transient_status() -> None:
    calls: list[float] = []

    def operation(remaining_seconds: float) -> str:
        calls.append(remaining_seconds)
        if len(calls) == 1:
            raise _status_error(503)
        return "ok"

    assert call_with_bounded_provider_retry(operation, timeout_seconds=30, max_retries=1) == "ok"
    assert len(calls) == 2
    assert calls[1] <= calls[0]


def test_does_not_retry_authentication_status() -> None:
    calls = 0

    def operation(_remaining_seconds: float) -> str:
        nonlocal calls
        calls += 1
        raise _status_error(401)

    with pytest.raises(APIStatusError):
        call_with_bounded_provider_retry(operation, timeout_seconds=30, max_retries=1)
    assert calls == 1


def test_stops_after_configured_retry_count() -> None:
    calls = 0

    def operation(_remaining_seconds: float) -> str:
        nonlocal calls
        calls += 1
        raise _status_error(502)

    with pytest.raises(APIStatusError):
        call_with_bounded_provider_retry(operation, timeout_seconds=30, max_retries=1)
    assert calls == 2


def test_retries_one_invalid_structured_result() -> None:
    calls = 0

    def operation(_remaining_seconds: float) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise StructuredOutputError("EvidenceFindings", candidate_count=1, issues=("findings:missing",))
        return "ok"

    assert (
        call_with_bounded_provider_retry(
            operation,
            timeout_seconds=30,
            max_retries=1,
            retryable_result_errors=(StructuredOutputError,),
        )
        == "ok"
    )
    assert calls == 2


def test_rejects_structured_result_after_single_retry() -> None:
    calls = 0

    def operation(_remaining_seconds: float) -> str:
        nonlocal calls
        calls += 1
        raise StructuredOutputError("EvidenceFindings", candidate_count=1, issues=("findings:missing",))

    with pytest.raises(StructuredOutputError):
        call_with_bounded_provider_retry(
            operation,
            timeout_seconds=30,
            max_retries=1,
            retryable_result_errors=(StructuredOutputError,),
        )
    assert calls == 2
