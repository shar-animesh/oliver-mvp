"""Regression tests for the restored canonical scoring contract."""

import unittest

from utils.scoring import DimensionScore, DIStage, assess_email, consolidate_dimensions
from utils.scoring.service import COMPLETENESS_FLOOR, email_to_submission
from utils.scoring.weights import DIMENSIONS, active_weight_set
from utils.transition_policy import CriterionFinding, CriterionRole, CriterionState, GateOutcome, policy_for_stage


class CanonicalScoringTests(unittest.TestCase):
    def test_all_stage_weights_total_one_hundred(self) -> None:
        weight_set = active_weight_set()
        for stage, weights in weight_set.weights.items():
            self.assertEqual(sum(weights[dimension] for dimension in DIMENSIONS), 100, stage)

    def test_thin_email_holds_for_evidence(self) -> None:
        assessment = assess_email("Something AI", "We should do something with AI for our work.")
        completeness = next(dimension for dimension in assessment.dimensions if dimension.dimension == "ideaCompleteness")
        self.assertIsNone(completeness.value)
        self.assertEqual(completeness.state, CriterionState.UNKNOWN)
        self.assertIsNone(assessment.composite_score)
        self.assertEqual(assessment.gate_outcome, GateOutcome.HOLD_FOR_EVIDENCE)

    def test_fallback_score_does_not_claim_transition_readiness(self) -> None:
        assessment = assess_email(
            "Predictive maintenance for gas turbines",
            """
            <p>Unplanned turbine downtime costs 2M EUR per year and affects service availability.</p>
            <p>We will use anomaly detection on PI System sensor data to provide 48-hour warnings.</p>
            <p>The VP of Gas Services sponsors the idea. A team of four is ready to run a pilot next quarter,
            targeting a 30% reduction in outages.</p>
            """,
        )
        self.assertEqual(len(assessment.dimensions), 5)
        self.assertIsNotNone(assessment.composite_score)
        self.assertGreaterEqual(assessment.composite_score or 0, COMPLETENESS_FLOOR)
        self.assertEqual(assessment.gate_outcome, GateOutcome.HOLD_FOR_EVIDENCE)

    def test_same_email_is_deterministic(self) -> None:
        first = assess_email("Contract review", "Manual review takes 3 weeks. We will use NLP on archived contracts.")
        second = assess_email("Contract review", "Manual review takes 3 weeks. We will use NLP on archived contracts.")
        self.assertEqual(first.model_dump(), second.model_dump())

    def test_html_is_normalized_without_markup(self) -> None:
        submission = email_to_submission("Re: Blade inspection", "<p>Inspectors review <strong>2,000 images</strong> every month.</p>")
        self.assertNotIn("<strong>", submission.problem_statement)
        self.assertEqual(submission.title, "Blade inspection")

    def test_quoted_history_is_not_treated_as_new_evidence(self) -> None:
        submission = email_to_submission(
            "Re: Contract review",
            "<p>I will confirm the owner.</p><p>From: Oliver</p><p>Previous invented score: 99/100</p>",
        )
        self.assertNotIn("99/100", submission.problem_statement)

    def test_evaluator_cannot_override_canonical_weights_or_stage_policy(self) -> None:
        dimensions = [
            DimensionScore(
                agent="untrusted",
                dimension=dimension,
                dimension_label="untrusted",
                state=CriterionState.SATISFIED,
                value=80,
                confidence=0.9,
                weight=100,
                summary="Evidence supports this canonical assessment dimension.",
                evidence=["Verified evidence supplied by the submitter"],
                gaps=[],
                scored_by="test-evaluator",
            )
            for dimension in DIMENSIONS
        ]
        assessment = consolidate_dimensions(dimensions, DIStage.DI2, model_version="test-model")
        expected_weights = active_weight_set().weights_for("DI2")

        self.assertEqual(assessment.composite_score, 80)
        self.assertEqual(assessment.current_stage, DIStage.DI2)
        self.assertIsNone(assessment.recommended_next_stage)
        self.assertEqual(assessment.model_version, "test-model")
        self.assertEqual(
            {dimension.dimension: dimension.weight for dimension in assessment.dimensions},
            expected_weights,
        )
        self.assertTrue(all(dimension.agent != "untrusted" for dimension in assessment.dimensions))

    def test_consolidation_rejects_duplicate_or_missing_dimensions(self) -> None:
        invalid_dimensions = [
            DimensionScore(
                agent="test",
                dimension="ideaCompleteness",
                dimension_label="test",
                state=CriterionState.SATISFIED,
                value=80,
                confidence=0.9,
                weight=0,
                summary="Evidence supports this canonical assessment dimension.",
                evidence=[],
                gaps=[],
            )
            for _ in DIMENSIONS
        ]
        with self.assertRaises(ValueError):
            consolidate_dimensions(invalid_dimensions, DIStage.DI1)

    def test_portfolio_score_cannot_change_transition_outcome(self) -> None:
        policy = policy_for_stage(DIStage.DI1)
        assert policy is not None
        findings = [
            CriterionFinding(
                criterion_id=criterion.criterion_id,
                state=(CriterionState.UNKNOWN if criterion.role == CriterionRole.BLOCKING_CONDITION else CriterionState.SATISFIED),
                confidence=0.9,
                summary="The approved criterion has been evaluated from the supplied evidence.",
                evidence=[] if criterion.role == CriterionRole.BLOCKING_CONDITION else ["Supplied evidence"],
                gaps=[],
            )
            for criterion in policy.criteria
        ]

        def dimensions(value: int) -> list[DimensionScore]:
            return [
                DimensionScore(
                    agent="test",
                    dimension=dimension,
                    dimension_label="test",
                    state=CriterionState.SATISFIED,
                    value=value,
                    confidence=0.9,
                    weight=0,
                    summary="Evidence supports a numeric portfolio comparison.",
                    evidence=["Supplied evidence"],
                    gaps=[],
                )
                for dimension in DIMENSIONS
            ]

        low_score = consolidate_dimensions(dimensions(35), DIStage.DI1, criterion_findings=findings)
        high_score = consolidate_dimensions(dimensions(95), DIStage.DI1, criterion_findings=findings)
        self.assertEqual(low_score.composite_score, 35)
        self.assertEqual(high_score.composite_score, 95)
        self.assertEqual(low_score.gate_outcome, GateOutcome.ADVANCE)
        self.assertEqual(high_score.gate_outcome, GateOutcome.ADVANCE)


if __name__ == "__main__":
    unittest.main()
