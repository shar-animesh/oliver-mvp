"""Deterministic lifecycle state machine for canonical Oliver assessments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from utils.audit import Auditor
from utils.postgres import InitiativeDb, LifecycleTransitionDb
from utils.scoring import CanonicalAssessment, DIStage
from utils.transition_policy import GateOutcome

POLICY_VERSION = "lifecycle/1.0.0"


class LifecycleConflictError(RuntimeError):
    """The initiative changed after a lifecycle decision began."""


class LifecycleDecisionError(ValueError):
    """A requested human lifecycle command violates current policy or state."""


@dataclass(frozen=True)
class TransitionInstruction:
    """A policy result that can be persisted without further model judgement."""

    transition_type: str
    from_stage: DIStage
    to_stage: DIStage | None
    requires_human_review: bool
    reason: str


def transition_for_assessment(
    *,
    current_stage: DIStage,
    is_on_hold: bool,
    assessment: CanonicalAssessment,
) -> TransitionInstruction | None:
    """Return the single allowed lifecycle action for an assessment."""
    if assessment.current_stage != current_stage:
        raise LifecycleConflictError(f"Assessment evaluated {assessment.current_stage.value}, but initiative is at {current_stage.value}")
    if assessment.gate_outcome == GateOutcome.HOLD_FOR_EVIDENCE:
        return None
    if assessment.gate_outcome == GateOutcome.CONTINUE_MONITORING:
        if current_stage != DIStage.DI5:
            raise LifecycleConflictError("Continue-monitoring is only valid for the terminal DI5 stage")
        return None
    if assessment.gate_outcome == GateOutcome.DO_NOT_ADVANCE:
        return TransitionInstruction(
            transition_type="NO_GO",
            from_stage=current_stage,
            to_stage=None,
            requires_human_review=True,
            reason=f"{assessment.transition_rationale} A Do-Not-Advance decision requires human approval.",
        )

    next_stage = assessment.recommended_next_stage
    if next_stage is None:
        raise LifecycleConflictError("An advance recommendation has no target stage")
    if next_stage != current_stage.next_stage:
        raise LifecycleConflictError("An advance recommendation must target the immediately following stage")
    review_reason: str | None = None
    if is_on_hold:
        review_reason = "The initiative is on hold and cannot advance until an authorized admin resumes it."
    elif next_stage == DIStage.DI5:
        review_reason = "Progression to DI5 Scale always requires human approval."
    elif assessment.requires_human_review:
        review_reason = "The assessment requires human review under the confidence policy."
    return TransitionInstruction(
        transition_type="ADVANCE",
        from_stage=current_stage,
        to_stage=next_stage,
        requires_human_review=review_reason is not None,
        reason=review_reason or assessment.transition_rationale,
    )


class StageMaster:
    """Persist lifecycle proposals and apply only policy-authorized movement."""

    def __init__(self, auditor: Auditor | None = None) -> None:
        self._auditor = auditor or Auditor()

    def process_assessment(
        self,
        database: Session,
        *,
        initiative: InitiativeDb,
        assessment: CanonicalAssessment,
        assessment_run_id: UUID,
    ) -> LifecycleTransitionDb | None:
        """Record an assessment and apply or propose its lifecycle consequence."""
        current_stage = DIStage(initiative.current_stage)
        self._auditor.record(
            database,
            event_type="ASSESSMENT_RECORDED",
            initiative_id=initiative.id,
            subject_type="canonical_assessment",
            subject_id=assessment_run_id,
            correlation_id=assessment_run_id,
            payload={
                "current_stage": assessment.current_stage.value,
                "transition_target": assessment.transition_target.value if assessment.transition_target is not None else None,
                "gate_outcome": assessment.gate_outcome.value,
                "composite_score": assessment.composite_score,
                "requires_human_review": assessment.requires_human_review,
                "model_version": assessment.model_version,
                "weight_set_version": assessment.weight_set_version,
                "transition_policy_version": assessment.transition_policy_version,
            },
        )
        instruction = transition_for_assessment(
            current_stage=current_stage,
            is_on_hold=initiative.is_on_hold,
            assessment=assessment,
        )
        if instruction is None:
            if initiative.is_on_hold:
                desired_state = "OnHold"
            elif assessment.gate_outcome == GateOutcome.HOLD_FOR_EVIDENCE:
                desired_state = "Stalled"
            else:
                desired_state = "Active"
            self._set_lifecycle_state(database, initiative, desired_state)
            return None

        now = datetime.now(timezone.utc)
        transition = LifecycleTransitionDb(
            initiative_id=initiative.id,
            assessment_run_id=assessment_run_id,
            transition_type=instruction.transition_type,
            from_stage=instruction.from_stage.value,
            to_stage=instruction.to_stage.value if instruction.to_stage is not None else None,
            status="PENDING" if instruction.requires_human_review else "APPLIED",
            requires_human_review=instruction.requires_human_review,
            expected_initiative_version=initiative.version,
            policy_version=assessment.transition_policy_version,
            reason=instruction.reason,
            proposed_by="StageMaster",
            decided_by=None if instruction.requires_human_review else "StageMaster",
            decided_at=None if instruction.requires_human_review else now,
        )
        database.add(transition)
        database.flush()

        if instruction.requires_human_review:
            event_type = "LIFECYCLE_REVIEW_REQUESTED"
        else:
            if instruction.to_stage is None:
                raise RuntimeError("An automatic advance requires a destination stage")
            self._apply_automatic_advance(database, initiative, instruction.to_stage)
            event_type = "STAGE_ADVANCED"

        self._auditor.record(
            database,
            event_type=event_type,
            initiative_id=initiative.id,
            subject_type="lifecycle_transition",
            subject_id=transition.id,
            correlation_id=assessment_run_id,
            payload={
                "transition_type": transition.transition_type,
                "from_stage": transition.from_stage,
                "to_stage": transition.to_stage,
                "status": transition.status,
                "requires_human_review": transition.requires_human_review,
                "reason": transition.reason,
                "policy_version": transition.policy_version,
            },
        )
        return transition

    def hold(self, database: Session, *, initiative_id: UUID, reason: str, actor_id: str) -> LifecycleTransitionDb:
        """Place an initiative on an explicit human hold."""
        initiative = self._locked_initiative(database, initiative_id)
        if initiative.is_on_hold:
            raise LifecycleDecisionError("Initiative is already on hold")
        transition = self._human_state_transition(
            database,
            initiative=initiative,
            transition_type="HOLD",
            reason=reason,
            actor_id=actor_id,
        )
        self._update_locked_initiative(
            database,
            initiative,
            is_on_hold=True,
            hold_reason=reason,
            lifecycle_state="OnHold",
        )
        self._audit_human_transition(database, transition, actor_id, "INITIATIVE_HELD")
        return transition

    def resume(self, database: Session, *, initiative_id: UUID, reason: str, actor_id: str) -> LifecycleTransitionDb:
        """Resume a held initiative without silently applying old proposals."""
        initiative = self._locked_initiative(database, initiative_id)
        if not initiative.is_on_hold:
            raise LifecycleDecisionError("Initiative is not on hold")
        transition = self._human_state_transition(
            database,
            initiative=initiative,
            transition_type="RESUME",
            reason=reason,
            actor_id=actor_id,
        )
        self._update_locked_initiative(
            database,
            initiative,
            is_on_hold=False,
            hold_reason=None,
            lifecycle_state="Active",
        )
        self._audit_human_transition(database, transition, actor_id, "INITIATIVE_RESUMED")
        return transition

    def decide_transition(
        self,
        database: Session,
        *,
        transition_id: UUID,
        approve: bool,
        reason: str,
        actor_id: str,
    ) -> LifecycleTransitionDb:
        """Approve or reject one pending proposal under optimistic concurrency."""
        transition = database.scalar(select(LifecycleTransitionDb).where(LifecycleTransitionDb.id == transition_id).with_for_update())
        if transition is None:
            raise LifecycleDecisionError("Lifecycle transition was not found")
        if transition.status != "PENDING":
            raise LifecycleDecisionError("Lifecycle transition has already been decided")
        initiative = self._locked_initiative(database, transition.initiative_id)
        if initiative.version != transition.expected_initiative_version:
            raise LifecycleConflictError("Initiative changed after this proposal was created; reassessment is required")
        if approve and initiative.is_on_hold:
            raise LifecycleDecisionError("Resume the initiative before approving a stage decision")

        transition.status = "APPROVED" if approve else "REJECTED"
        transition.decided_by = actor_id
        transition.decided_at = datetime.now(timezone.utc)
        transition.reason = f"{transition.reason}\nHuman decision: {reason.strip()}"
        if approve:
            if transition.transition_type == "ADVANCE":
                if transition.to_stage is None:
                    raise LifecycleDecisionError("Advance proposal has no destination stage")
                self._update_locked_initiative(
                    database,
                    initiative,
                    current_stage=transition.to_stage,
                    lifecycle_state="Active",
                    stage_entered_at=datetime.now(timezone.utc),
                )
            elif transition.transition_type == "NO_GO":
                self._update_locked_initiative(database, initiative, lifecycle_state="NoGo")
            else:
                raise LifecycleDecisionError(f"Unsupported pending transition type {transition.transition_type}")
        self._audit_human_transition(
            database,
            transition,
            actor_id,
            "LIFECYCLE_DECISION_APPROVED" if approve else "LIFECYCLE_DECISION_REJECTED",
        )
        return transition

    @staticmethod
    def _apply_automatic_advance(database: Session, initiative: InitiativeDb, next_stage: DIStage) -> None:
        expected_version = initiative.version
        result = database.execute(
            update(InitiativeDb)
            .where(InitiativeDb.id == initiative.id, InitiativeDb.version == expected_version)
            .values(
                current_stage=next_stage.value,
                lifecycle_state="Active",
                version=expected_version + 1,
                stage_entered_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount != 1:
            raise LifecycleConflictError(f"Initiative {initiative.id} changed during automatic stage progression")
        database.refresh(initiative)

    @staticmethod
    def _set_lifecycle_state(database: Session, initiative: InitiativeDb, lifecycle_state: str) -> None:
        if initiative.lifecycle_state == lifecycle_state:
            return
        expected_version = initiative.version
        result = database.execute(
            update(InitiativeDb)
            .where(InitiativeDb.id == initiative.id, InitiativeDb.version == expected_version)
            .values(lifecycle_state=lifecycle_state, version=expected_version + 1)
        )
        if result.rowcount != 1:
            raise LifecycleConflictError(f"Initiative {initiative.id} changed while updating lifecycle state")
        database.refresh(initiative)

    @staticmethod
    def _locked_initiative(database: Session, initiative_id: UUID) -> InitiativeDb:
        initiative = database.scalar(select(InitiativeDb).where(InitiativeDb.id == initiative_id).with_for_update())
        if initiative is None:
            raise LifecycleDecisionError("Initiative was not found")
        return initiative

    @staticmethod
    def _update_locked_initiative(database: Session, initiative: InitiativeDb, **values: object) -> None:
        expected_version = initiative.version
        result = database.execute(
            update(InitiativeDb)
            .where(InitiativeDb.id == initiative.id, InitiativeDb.version == expected_version)
            .values(**values, version=expected_version + 1)
        )
        if result.rowcount != 1:
            raise LifecycleConflictError(f"Initiative {initiative.id} changed during the lifecycle command")
        database.refresh(initiative)

    @staticmethod
    def _human_state_transition(
        database: Session,
        *,
        initiative: InitiativeDb,
        transition_type: str,
        reason: str,
        actor_id: str,
    ) -> LifecycleTransitionDb:
        transition = LifecycleTransitionDb(
            initiative_id=initiative.id,
            transition_type=transition_type,
            from_stage=initiative.current_stage,
            to_stage=initiative.current_stage,
            status="APPLIED",
            requires_human_review=True,
            expected_initiative_version=initiative.version,
            policy_version=POLICY_VERSION,
            reason=reason.strip(),
            proposed_by=actor_id,
            decided_by=actor_id,
            decided_at=datetime.now(timezone.utc),
        )
        database.add(transition)
        database.flush()
        return transition

    def _audit_human_transition(
        self,
        database: Session,
        transition: LifecycleTransitionDb,
        actor_id: str,
        event_type: str,
    ) -> None:
        self._auditor.record(
            database,
            event_type=event_type,
            initiative_id=transition.initiative_id,
            actor_type="USER",
            actor_id=actor_id,
            subject_type="lifecycle_transition",
            subject_id=transition.id,
            correlation_id=transition.assessment_run_id,
            payload={
                "transition_type": transition.transition_type,
                "from_stage": transition.from_stage,
                "to_stage": transition.to_stage,
                "status": transition.status,
                "reason": transition.reason,
                "policy_version": transition.policy_version,
            },
        )
