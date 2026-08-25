"""Contract tests for deterministic Pacer cadence rules."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from utils.pacer import cadence_for

_SLA = {"DI1": 30, "DI2": 60, "DI3": 90, "DI4": 120}


def _initiative(*, stage: str, days: int, on_hold: bool = False, state: str = "Active"):
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return now, SimpleNamespace(
        id=uuid4(),
        current_stage=stage,
        stage_entered_at=now - timedelta(days=days),
        is_on_hold=on_hold,
        lifecycle_state=state,
    )


class PacerPolicyTests(unittest.TestCase):
    def test_stage_is_not_stalled_before_its_sla(self) -> None:
        now, initiative = _initiative(stage="DI1", days=29)
        result = cadence_for(initiative, now=now, stage_sla_days=_SLA)
        self.assertFalse(result.stall_flag)
        self.assertEqual(result.days_to_next_gate, 1)

    def test_stage_stalls_when_sla_is_reached(self) -> None:
        now, initiative = _initiative(stage="DI2", days=60)
        result = cadence_for(initiative, now=now, stage_sla_days=_SLA)
        self.assertTrue(result.stall_flag)
        self.assertEqual(result.days_to_next_gate, 0)

    def test_hold_suspends_stall_detection(self) -> None:
        now, initiative = _initiative(stage="DI3", days=120, on_hold=True)
        result = cadence_for(initiative, now=now, stage_sla_days=_SLA)
        self.assertFalse(result.stall_flag)

    def test_scale_is_terminal_without_a_next_gate(self) -> None:
        now, initiative = _initiative(stage="DI5", days=365)
        result = cadence_for(initiative, now=now, stage_sla_days=_SLA)
        self.assertFalse(result.stall_flag)
        self.assertIsNone(result.days_to_next_gate)


if __name__ == "__main__":
    unittest.main()
