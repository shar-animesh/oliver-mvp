"""Contract tests for Sentinel threshold policy and Realizer progress math."""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from utils.operations import Realizer, Sentinel, threshold_breached


class OperationsPolicyTests(unittest.TestCase):
    def test_minimum_slo_breaches_below_threshold(self) -> None:
        self.assertTrue(threshold_breached(value=79, threshold=80, direction="AT_LEAST"))
        self.assertFalse(threshold_breached(value=80, threshold=80, direction="AT_LEAST"))

    def test_maximum_slo_breaches_above_threshold(self) -> None:
        self.assertTrue(threshold_breached(value=11, threshold=10, direction="AT_MOST"))
        self.assertFalse(threshold_breached(value=10, threshold=10, direction="AT_MOST"))

    def test_realizer_progress_for_increasing_value(self) -> None:
        metric = SimpleNamespace(baseline=100.0, threshold=200.0, direction="AT_LEAST")
        self.assertEqual(Realizer._progress(metric, 150.0), 50.0)

    def test_realizer_progress_for_reduction_target(self) -> None:
        metric = SimpleNamespace(baseline=100.0, threshold=60.0, direction="AT_MOST")
        self.assertEqual(Realizer._progress(metric, 80.0), 50.0)

    def test_idempotency_replay_rejects_a_different_observation_payload(self) -> None:
        observed_at = datetime(2026, 8, 25, tzinfo=timezone.utc)
        existing = SimpleNamespace(
            metric_id="metric-1",
            value=10.0,
            source_reference="sample-1",
            observed_at=observed_at,
            measurement_metadata={"window": "5m"},
            metric=SimpleNamespace(source_system="monitoring"),
            alert=None,
        )
        database = SimpleNamespace(scalar=lambda _statement: existing)

        with self.assertRaisesRegex(ValueError, "different observation payload"):
            Sentinel().record_observation(
                database,
                metric_id="metric-1",
                idempotency_key="observation-1",
                value=11.0,
                source_system="monitoring",
                source_reference="sample-1",
                observed_at=observed_at,
                metadata={"window": "5m"},
                actor_id="test",
            )


if __name__ == "__main__":
    unittest.main()
