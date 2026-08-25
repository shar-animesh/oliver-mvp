"""Regression tests for bounded and trustworthy evidence ingestion."""

import unittest
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from pydantic import ValidationError

from utils.attachments.service import AttachmentValidationError, _validate_archive_size
from utils.email_content import current_message_text, html_to_text
from utils.models.api.email import MAX_ATTACHMENTS_PER_MESSAGE, EmailAttachmentInput, EmailResponseRequest
from utils.models.api.operations import MetricDefinitionRequest, MetricObservationRequest
from utils.templates.loader import render_oliver_email


class EmailNormalizationTests(unittest.TestCase):
    def test_standard_signature_delimiter_removes_signature(self) -> None:
        self.assertEqual(current_message_text("<p>Current evidence</p><p>-- </p><p>Employee Name</p>"), "Current evidence")

    def test_script_and_style_content_are_not_evidence(self) -> None:
        text = html_to_text("<style>.hidden{display:none}</style><p>Current evidence</p><script>alert(1)</script>")
        self.assertEqual(text, "Current evidence")

    def test_html_entities_are_decoded_once(self) -> None:
        self.assertEqual(html_to_text("<p>&amp;lt;threshold&amp;gt;</p>"), "&lt;threshold&gt;")

    def test_model_generated_email_html_is_sanitized(self) -> None:
        rendered = render_oliver_email(
            subject="Test",
            content_html=(
                '<p>Safe</p><script>alert(1)</script><img src="https://tracker.invalid/pixel">'
                '<a href="javascript:alert(2)">unsafe</a><a href="https://example.com">safe link</a>'
            ),
        )
        self.assertNotIn("<script", rendered)
        self.assertNotIn('<img src="https://tracker.invalid', rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertIn('href="https://example.com"', rendered)


class AttachmentLimitTests(unittest.TestCase):
    def test_archive_expansion_above_limit_is_rejected_before_extraction(self) -> None:
        content = BytesIO()
        with ZipFile(content, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", "x" * 100)

        with self.assertRaises(AttachmentValidationError):
            _validate_archive_size(content.getvalue(), maximum=50)

    def test_attachment_count_is_bounded_at_the_api_contract(self) -> None:
        attachments = [
            EmailAttachmentInput(
                attachment_id=str(index),
                file_name=f"evidence-{index}.pdf",
                content_type="application/pdf",
                content_base64="YQ==",
            )
            for index in range(MAX_ATTACHMENTS_PER_MESSAGE + 1)
        ]
        with self.assertRaises(ValidationError):
            EmailResponseRequest(
                message_id="message-1",
                conversation_id="conversation-1",
                received_at="2026-08-25T00:00:00Z",
                email_thread="Evidence",
                attachments=attachments,
            )


class MetricContractTests(unittest.TestCase):
    def test_non_finite_threshold_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            MetricDefinitionRequest(
                name="Availability",
                metric_type="SLO",
                unit="percent",
                direction="AT_LEAST",
                threshold=float("nan"),
                source_system="monitoring",
            )

    def test_non_finite_observation_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            MetricObservationRequest(
                idempotency_key="observation-1",
                value=float("inf"),
                source_system="monitoring",
                source_reference="sample-1",
                observed_at="2026-08-25T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
