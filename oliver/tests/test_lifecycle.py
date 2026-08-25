"""Contract tests for deterministic lifecycle authority rules."""

import unittest
from types import SimpleNamespace
from uuid import uuid4

from utils.lifecycle import LifecycleConflictError, StageMaster, transition_for_assessment
from utils.scoring import DIStage, assess_email
from utils.transition_policy import GateOutcome


def _passing_assessment(stage: DIStage):
    assessment = assess_email(
        "Predictive maintenance for gas turbines",
        """
        Unplanned turbine downtime costs 2M EUR per year and affects service availability.
        We will use anomaly detection on PI System sensor data to provide 48-hour warnings.
        The VP of Gas Services sponsors the idea. A team of four engineers is ready to run
        a pilot next quarter, targeting a 30% reduction in outages within three months.
        """,
        stage,
    )
    return assessment.model_copy(
        update={
            "transition_target": stage.next_stage,
            "recommended_next_stage": stage.next_stage,
            "gate_outcome": GateOutcome.ADVANCE,
            "requires_human_review": False,
        }
    )


class LifecyclePolicyTests(unittest.TestCase):
    def test_di1_pass_advances_automatically_to_di2(self) -> None:
        instruction = transition_for_assessment(
            current_stage=DIStage.DI1,
            is_on_hold=False,
            assessment=_passing_assessment(DIStage.DI1),
        )
        self.assertIsNotNone(instruction)
        assert instruction is not None
        self.assertEqual(instruction.to_stage, DIStage.DI2)
        self.assertFalse(instruction.requires_human_review)

    def test_di4_pass_requires_human_approval_for_scale(self) -> None:
        instruction = transition_for_assessment(
            current_stage=DIStage.DI4,
            is_on_hold=False,
            assessment=_passing_assessment(DIStage.DI4),
        )
        self.assertIsNotNone(instruction)
        assert instruction is not None
        self.assertEqual(instruction.to_stage, DIStage.DI5)
        self.assertTrue(instruction.requires_human_review)

    def test_hold_blocks_automatic_progression(self) -> None:
        instruction = transition_for_assessment(
            current_stage=DIStage.DI2,
            is_on_hold=True,
            assessment=_passing_assessment(DIStage.DI2),
        )
        self.assertIsNotNone(instruction)
        assert instruction is not None
        self.assertTrue(instruction.requires_human_review)
        self.assertIn("hold", instruction.reason.lower())

    def test_no_go_is_a_human_decision_without_automatic_rollback(self) -> None:
        assessment = _passing_assessment(DIStage.DI3).model_copy(update={"recommended_next_stage": None, "gate_outcome": GateOutcome.DO_NOT_ADVANCE})
        instruction = transition_for_assessment(
            current_stage=DIStage.DI3,
            is_on_hold=False,
            assessment=assessment,
        )
        self.assertIsNotNone(instruction)
        assert instruction is not None
        self.assertEqual(instruction.transition_type, "NO_GO")
        self.assertIsNone(instruction.to_stage)
        self.assertTrue(instruction.requires_human_review)

    def test_hold_for_evidence_does_not_move_stage(self) -> None:
        assessment = _passing_assessment(DIStage.DI2).model_copy(
            update={"recommended_next_stage": None, "gate_outcome": GateOutcome.HOLD_FOR_EVIDENCE}
        )
        instruction = transition_for_assessment(
            current_stage=DIStage.DI2,
            is_on_hold=False,
            assessment=assessment,
        )
        self.assertIsNone(instruction)

    def test_assessment_does_not_clear_an_existing_manual_hold(self) -> None:
        assessment = _passing_assessment(DIStage.DI2).model_copy(
            update={"recommended_next_stage": None, "gate_outcome": GateOutcome.HOLD_FOR_EVIDENCE}
        )
        initiative = SimpleNamespace(
            id=uuid4(),
            current_stage=DIStage.DI2.value,
            is_on_hold=True,
            lifecycle_state="OnHold",
        )
        auditor = SimpleNamespace(record=lambda *_args, **_kwargs: None)

        transition = StageMaster(auditor=auditor).process_assessment(  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            initiative=initiative,
            assessment=assessment,
            assessment_run_id=uuid4(),
        )

        self.assertIsNone(transition)
        self.assertEqual(initiative.lifecycle_state, "OnHold")

    def test_stale_assessment_cannot_change_newer_stage(self) -> None:
        with self.assertRaises(LifecycleConflictError):
            transition_for_assessment(
                current_stage=DIStage.DI3,
                is_on_hold=False,
                assessment=_passing_assessment(DIStage.DI2),
            )

    def test_di5_assessment_never_creates_a_forward_transition(self) -> None:
        assessment = assess_email(
            "Scaled predictive maintenance service",
            "Please reassess current monitoring and realized value evidence for the deployed service.",
            DIStage.DI5,
        )
        self.assertEqual(assessment.gate_outcome, GateOutcome.CONTINUE_MONITORING)
        self.assertIsNone(assessment.transition_target)
        self.assertIsNone(
            transition_for_assessment(
                current_stage=DIStage.DI5,
                is_on_hold=False,
                assessment=assessment,
            )
        )


if __name__ == "__main__":
    unittest.main()
