"""Regression tests for evidence-state lifecycle recommendations."""

import unittest
from pathlib import Path

import pytest

from utils.scoring import DIStage
from utils.transition_policy import (
    BlockingBehavior,
    CriterionFinding,
    CriterionRole,
    CriterionState,
    CriterionTiming,
    GateOutcome,
    ReportDepth,
    StageTransitionPolicy,
    TransitionCriterion,
    active_transition_policy_set,
    evaluate_terminal_stage,
    evaluate_transition,
    policy_for_stage,
    terminal_policy_for_stage,
    unavailable_transition_evaluation,
)
from utils.transition_policy.loader import _load_policy_sets
from utils.transition_policy.presentation import participant_transition_recommendation, remove_internal_criterion_ids


def _assert_known_criteria(policy: StageTransitionPolicy, states: dict[str, CriterionState]) -> None:
    known_ids = {criterion.criterion_id for criterion in policy.criteria}
    unknown_ids = set(states) - known_ids
    if unknown_ids:
        raise AssertionError(f"Unknown criterion IDs for {policy.current_stage}: {sorted(unknown_ids)}")


def _findings(**states: CriterionState) -> list[CriterionFinding]:
    policy = policy_for_stage(DIStage.DI1)
    assert policy is not None
    _assert_known_criteria(policy, states)
    return [
        CriterionFinding(
            criterion_id=criterion.criterion_id,
            state=states.get(criterion.criterion_id, CriterionState.SATISFIED),
            confidence=0.9,
            summary=f"Evidence state for {criterion.title} is recorded without inference.",
            evidence=["Supplied evidence"] if states.get(criterion.criterion_id, CriterionState.SATISFIED) == CriterionState.SATISFIED else [],
            gaps=["Evidence is not supplied"] if states.get(criterion.criterion_id) == CriterionState.UNKNOWN else [],
        )
        for criterion in policy.criteria
    ]


def _findings_for(stage: DIStage, **states: CriterionState) -> list[CriterionFinding]:
    policy = policy_for_stage(stage)
    assert policy is not None
    _assert_known_criteria(policy, states)
    findings = []
    for criterion in policy.criteria:
        default_state = CriterionState.NOT_APPLICABLE if criterion.role == CriterionRole.BLOCKING_CONDITION else CriterionState.SATISFIED
        state = states.get(criterion.criterion_id, default_state)
        findings.append(
            CriterionFinding(
                criterion_id=criterion.criterion_id,
                state=state,
                confidence=0.9,
                summary=f"Evidence state for {criterion.title} is recorded without inference.",
                evidence=["Supplied evidence"] if state == CriterionState.SATISFIED else [],
                gaps=["Evidence is not supplied"] if state == CriterionState.UNKNOWN else [],
            )
        )
    return findings


def test_duplicate_policy_version_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    built_in = Path(__file__).parents[1] / "utils" / "transition_policy" / "data" / "transition-policy-1.1.0.json"
    (tmp_path / "duplicate.json").write_text(built_in.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("OLIVER_TRANSITION_POLICY_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="Duplicate transition policy version"):
        _load_policy_sets()


class TransitionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy_set = active_transition_policy_set()
        policy = policy_for_stage(DIStage.DI1)
        assert policy is not None
        self.policy = policy

    def evaluate(self, findings: list[CriterionFinding]):
        return evaluate_transition(
            self.policy,
            findings,
            policy_version=self.policy_set.version,
            confidence_floor=0.6,
        )

    def test_full_evidence_with_open_live_data_controls_conditionally_advances(self) -> None:
        result = self.evaluate(
            _findings(
                DI1_DI2_INTEGRATION_VALIDATION=CriterionState.UNKNOWN,
                DI1_DI2_LIVE_DATA_CONTROLS=CriterionState.UNKNOWN,
            )
        )
        self.assertEqual(result.gate_outcome, GateOutcome.CONDITIONAL_ADVANCE)
        self.assertEqual(result.recommended_next_stage, DIStage.DI2)
        self.assertEqual(result.response_depth, ReportDepth.STANDARD)

    def test_missing_entry_evidence_holds_without_calling_the_idea_bad(self) -> None:
        result = self.evaluate(
            _findings(
                DI1_DI2_ACCOUNTABLE_OWNER=CriterionState.UNKNOWN,
                DI1_DI2_PILOT_SCOPE=CriterionState.UNKNOWN,
            )
        )
        self.assertEqual(result.gate_outcome, GateOutcome.HOLD_FOR_EVIDENCE)
        self.assertIsNone(result.recommended_next_stage)
        self.assertEqual(result.response_depth, ReportDepth.BRIEF)
        self.assertNotIn("No-Go", result.rationale)

    def test_participant_recommendation_uses_plain_language_not_policy_ids(self) -> None:
        result = self.evaluate(
            _findings(
                DI1_DI2_PILOT_SCOPE=CriterionState.UNKNOWN,
                DI1_DI2_ACCOUNTABLE_OWNER=CriterionState.UNKNOWN,
                DI1_DI2_ACCEPTABLE_EXPERIMENT_RISK=CriterionState.UNKNOWN,
            )
        )
        recommendation = participant_transition_recommendation(result)  # type: ignore[arg-type]

        self.assertEqual(recommendation.label, "Hold for evidence")
        self.assertEqual(
            recommendation.detail,
            "Before moving to DI2, please clarify the pilot scope, confirm an accountable owner, and complete the experiment-risk check.",
        )
        self.assertEqual(recommendation.basis, "This recommendation is based on missing DI1 exit evidence.")
        self.assertNotIn("DI1_DI2_", recommendation.detail)

    def test_internal_policy_id_safety_filter(self) -> None:
        rendered = remove_internal_criterion_ids("Do not display DI1_DI2_PILOT_SCOPE to a participant.")
        self.assertEqual(rendered, "Do not display an internal policy criterion to a participant.")

    def test_actual_blocking_concern_produces_do_not_advance(self) -> None:
        result = self.evaluate(_findings(DI1_DI2_SOLUTION_NOT_VIABLE=CriterionState.CONCERN))
        self.assertEqual(result.gate_outcome, GateOutcome.DO_NOT_ADVANCE)
        self.assertTrue(result.requires_human_review)

    def test_management_pressure_cannot_change_a_policy_result(self) -> None:
        neutral_findings = _findings(DI1_DI2_ACCOUNTABLE_OWNER=CriterionState.UNKNOWN)
        pressured_findings = [finding.model_copy() for finding in neutral_findings]
        self.assertEqual(self.evaluate(neutral_findings), self.evaluate(pressured_findings))

    def test_unknown_next_stage_learning_does_not_block_entry(self) -> None:
        result = self.evaluate(
            _findings(
                DI1_DI2_LIVE_PERFORMANCE=CriterionState.UNKNOWN,
                DI1_DI2_INTEGRATION_VALIDATION=CriterionState.UNKNOWN,
                DI1_DI2_VALUE_VALIDATION=CriterionState.UNKNOWN,
                DI1_DI2_ADOPTION_VALIDATION=CriterionState.UNKNOWN,
                DI1_DI2_MONITORING_DESIGN=CriterionState.UNKNOWN,
                DI1_DI2_SCALABILITY_SIGNALS=CriterionState.UNKNOWN,
            )
        )
        self.assertEqual(result.gate_outcome, GateOutcome.ADVANCE)
        self.assertEqual(result.recommended_next_stage, DIStage.DI2)

    def test_unmentioned_blocker_does_not_become_a_blocker_or_low_confidence_exception(self) -> None:
        findings = _findings(
            DI1_DI2_SOLUTION_NOT_VIABLE=CriterionState.UNKNOWN,
            DI1_DI2_UNACCEPTABLE_SAFETY_RISK=CriterionState.UNKNOWN,
            DI1_DI2_NO_FEASIBLE_PILOT=CriterionState.UNKNOWN,
            DI1_DI2_PROHIBITED_DATA_COMPLIANCE=CriterionState.UNKNOWN,
        )
        findings = [finding.model_copy(update={"confidence": 0.1}) if finding.state == CriterionState.UNKNOWN else finding for finding in findings]
        result = self.evaluate(findings)
        self.assertEqual(result.gate_outcome, GateOutcome.ADVANCE)
        self.assertFalse(result.requires_human_review)

    def test_unapproved_later_transition_fails_safe(self) -> None:
        result = unavailable_transition_evaluation(DIStage.DI2, "missing-policy/test")
        self.assertEqual(result.gate_outcome, GateOutcome.HOLD_FOR_EVIDENCE)
        self.assertFalse(result.policy_available)
        self.assertTrue(result.requires_human_review)

    def test_every_forward_stage_has_an_approved_policy(self) -> None:
        expected = {
            DIStage.DI1: DIStage.DI2,
            DIStage.DI2: DIStage.DI3,
            DIStage.DI3: DIStage.DI4,
            DIStage.DI4: DIStage.DI5,
        }
        for current_stage, target_stage in expected.items():
            with self.subTest(current_stage=current_stage):
                policy = policy_for_stage(current_stage)
                self.assertIsNotNone(policy)
                assert policy is not None
                self.assertEqual(policy.target_stage, target_stage)

    def test_forward_policy_rejects_terminal_monitoring_criteria(self) -> None:
        entry = TransitionCriterion(
            criterion_id="DI1_DI2_ENTRY",
            title="Entry criterion",
            description="Evidence required before entering the next stage.",
            user_action="Provide the required entry evidence.",
            role=CriterionRole.ENTRY_CRITERION,
            timing=CriterionTiming.REQUIRED_BEFORE_ENTRY,
            blocking_behavior=BlockingBehavior.BLOCK_ON_CONCERN,
            source="test policy",
        )
        terminal = TransitionCriterion(
            criterion_id="DI1_DI2_MONITORING",
            title="Terminal monitoring",
            description="Monitoring belongs only to the terminal-stage policy.",
            user_action="Continue monitoring realized value.",
            role=CriterionRole.TERMINAL_MONITORING,
            timing=CriterionTiming.REQUIRED_DURING_STAGE,
            blocking_behavior=BlockingBehavior.NON_BLOCKING,
            source="test policy",
        )

        with pytest.raises(ValueError, match="cannot be used in a forward transition policy"):
            StageTransitionPolicy(
                current_stage=DIStage.DI1,
                target_stage=DIStage.DI2,
                current_stage_objective="Establish whether the idea is credible enough to pilot.",
                next_stage_objective="Test the idea under controlled and realistic conditions.",
                criteria=[entry, terminal],
            )

    def test_all_satisfied_evidence_advances_each_forward_stage(self) -> None:
        for stage in (DIStage.DI1, DIStage.DI2, DIStage.DI3, DIStage.DI4):
            with self.subTest(stage=stage):
                policy = policy_for_stage(stage)
                assert policy is not None
                result = evaluate_transition(
                    policy,
                    _findings_for(stage),
                    policy_version=self.policy_set.version,
                    confidence_floor=0.6,
                )
                self.assertEqual(result.gate_outcome, GateOutcome.ADVANCE)
                self.assertEqual(result.recommended_next_stage, stage.next_stage)
                self.assertEqual(result.requires_human_review, stage == DIStage.DI4)

    def test_unknown_entry_evidence_holds_each_forward_stage(self) -> None:
        for stage in (DIStage.DI1, DIStage.DI2, DIStage.DI3, DIStage.DI4):
            with self.subTest(stage=stage):
                policy = policy_for_stage(stage)
                assert policy is not None
                entry = next(criterion for criterion in policy.criteria if criterion.role == CriterionRole.ENTRY_CRITERION)
                result = evaluate_transition(
                    policy,
                    _findings_for(stage, **{entry.criterion_id: CriterionState.UNKNOWN}),
                    policy_version=self.policy_set.version,
                    confidence_floor=0.6,
                )
                self.assertEqual(result.gate_outcome, GateOutcome.HOLD_FOR_EVIDENCE)

    def test_management_pressure_cannot_change_any_forward_transition(self) -> None:
        for stage in (DIStage.DI1, DIStage.DI2, DIStage.DI3, DIStage.DI4):
            with self.subTest(stage=stage):
                policy = policy_for_stage(stage)
                assert policy is not None
                entry = next(criterion for criterion in policy.criteria if criterion.role == CriterionRole.ENTRY_CRITERION)
                neutral = _findings_for(stage, **{entry.criterion_id: CriterionState.UNKNOWN})
                pressured = [finding.model_copy() for finding in neutral]
                neutral_result = evaluate_transition(
                    policy,
                    neutral,
                    policy_version=self.policy_set.version,
                    confidence_floor=0.6,
                )
                pressured_result = evaluate_transition(
                    policy,
                    pressured,
                    policy_version=self.policy_set.version,
                    confidence_floor=0.6,
                )
                self.assertEqual(neutral_result, pressured_result)

    def test_di5_is_terminal_monitoring_not_a_forward_gate(self) -> None:
        policy = terminal_policy_for_stage(DIStage.DI5)
        assert policy is not None
        findings = [
            CriterionFinding(
                criterion_id=criterion.criterion_id,
                state=CriterionState.SATISFIED,
                confidence=0.9,
                summary=f"Current evidence supports {criterion.title}.",
                evidence=["Current sourced evidence"],
            )
            for criterion in policy.criteria
        ]
        result = evaluate_terminal_stage(
            policy,
            findings,
            policy_version=self.policy_set.version,
            confidence_floor=0.6,
        )
        self.assertEqual(result.gate_outcome, GateOutcome.CONTINUE_MONITORING)
        self.assertIsNone(result.transition_target)
        self.assertIsNone(result.recommended_next_stage)
        self.assertFalse(result.requires_human_review)


if __name__ == "__main__":
    unittest.main()
