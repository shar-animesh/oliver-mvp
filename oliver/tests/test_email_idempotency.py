"""Regression tests for provider replay handling at the email boundary."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from routes.email import _canonical_message_id, _is_replayed_message


def _message(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "internet_message_id": "<stable@example.test>",
        "direction": "INBOUND",
        "sender_email": "owner@example.test",
        "subject": "Pilot update",
        "content_html": "<p>Accuracy improved to 90%.</p>",
        "received_at": datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_provider_message_id_formatting_is_canonicalized() -> None:
    assert _canonical_message_id("  <Stable@Example.Test> ") == "stable@example.test"


def test_replay_with_different_item_id_matches_same_payload() -> None:
    existing = _message()
    assert _is_replayed_message(
        existing,
        message_id="connector-item-42",
        sender_email="OWNER@example.test",
        subject=" Pilot update ",
        content_html="<p>Accuracy improved to 90%.</p>",
        received_at=existing.received_at + timedelta(seconds=3),
    )


def test_different_body_is_not_suppressed_as_replay() -> None:
    existing = _message()
    assert not _is_replayed_message(
        existing,
        message_id="connector-item-43",
        sender_email="owner@example.test",
        subject="Pilot update",
        content_html="<p>Accuracy improved to 91%.</p>",
        received_at=existing.received_at + timedelta(minutes=11),
    )


def test_same_id_is_a_replay_even_if_provider_reformats_body() -> None:
    assert _is_replayed_message(
        _message(),
        message_id="stable@example.test",
        sender_email="different@example.test",
        subject="Different subject",
        content_html="<p>Different body.</p>",
        received_at=datetime(2026, 8, 30, 12, 30, tzinfo=timezone.utc),
    )


def test_retry_with_changed_outlook_quote_markup_matches_authored_text() -> None:
    existing = _message(
        subject="Re: Pilot update",
        content_html="<p>Added the baseline and owner.</p><p>From: Oliver &lt;oliver@example.test&gt;</p><p>old report</p>",
    )
    assert _is_replayed_message(
        existing,
        message_id="connector-item-44",
        sender_email="owner@example.test",
        subject="RE: Pilot update",
        content_html="<div>Added the baseline and owner.</div><blockquote><p>From: Oliver</p><p>new tracking markup</p></blockquote>",
        received_at=existing.received_at + timedelta(seconds=4),
    )
