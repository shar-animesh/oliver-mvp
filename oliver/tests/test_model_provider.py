"""Structured provider compatibility tests."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from utils.model_provider import StructuredOutputError, parse_structured_output


class _Result(BaseModel):
    answer: int


def _message(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_parser_uses_valid_json_after_separate_provider_preamble() -> None:
    response = SimpleNamespace(
        output=[
            _message("I will return the structured result now."),
            _message('{"answer":42}'),
        ]
    )

    assert parse_structured_output(response, _Result).answer == 42


def test_parser_accepts_fenced_json_but_not_invalid_objects() -> None:
    response = SimpleNamespace(output=[_message('```json\n{"wrong":1}\n```\n{"answer":7}')])

    assert parse_structured_output(response, _Result).answer == 7


def test_parser_rejects_response_without_valid_schema_object() -> None:
    response = SimpleNamespace(output=[_message('Result: {"wrong":1}')])

    with pytest.raises(StructuredOutputError) as captured:
        parse_structured_output(response, _Result)
    assert captured.value.candidate_count == 1
    assert captured.value.issues == ("answer:missing",)


def test_parser_reports_incomplete_response_without_exposing_content() -> None:
    response = SimpleNamespace(
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        output=[SimpleNamespace(content=[SimpleNamespace(type="output_text", text="sensitive non-json output")])],
    )

    with pytest.raises(StructuredOutputError) as captured:
        parse_structured_output(response, _Result)

    assert captured.value.issues == (
        "response_status:incomplete",
        "incomplete_reason:max_output_tokens",
        "content_types:output_text",
    )
    assert "sensitive" not in str(captured.value)
