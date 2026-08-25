"""Shared size limits for model-produced evidence findings."""

from typing import Annotated

from pydantic import StringConstraints

FINDING_SUMMARY_MAX_CHARS = 400
FINDING_ITEM_MAX_CHARS = 240
FINDING_ITEMS_MAX = 3

FindingStatement = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=FINDING_ITEM_MAX_CHARS),
]


def bound_finding_text(value: str, maximum_chars: int = FINDING_SUMMARY_MAX_CHARS) -> str:
    """Bound model-authored prose after parsing without altering source evidence."""
    normalized = " ".join(value.split())
    if len(normalized) <= maximum_chars:
        return normalized
    shortened = normalized[: maximum_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{shortened}…"


def bound_finding_items(values: list[str]) -> list[str]:
    """Keep a small, ordered set of concise model-authored evidence statements."""
    return [bound_finding_text(value, FINDING_ITEM_MAX_CHARS) for value in values[:FINDING_ITEMS_MAX]]
