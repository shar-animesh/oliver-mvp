"""Single mapping boundary from scoring contracts to PostgreSQL records."""

from uuid import UUID

from utils.postgres import CanonicalAssessmentDb

from .models import CanonicalAssessment


def apply_assessment(record: CanonicalAssessmentDb, assessment: CanonicalAssessment) -> CanonicalAssessmentDb:
    """Apply every canonical field to a new or existing database record."""
    record.current_stage = assessment.current_stage.value
    record.composite_score = assessment.composite_score
    record.transition_target = assessment.transition_target.value if assessment.transition_target is not None else None
    record.recommended_next_stage = assessment.recommended_next_stage.value if assessment.recommended_next_stage is not None else None
    record.gate_outcome = assessment.gate_outcome.value
    record.lifecycle_state = assessment.lifecycle_state.value
    record.composite_confidence = assessment.composite_confidence
    record.lowest_confidence_dimension = assessment.lowest_confidence_dimension
    record.requires_human_review = assessment.requires_human_review
    record.response_depth = assessment.response_depth.value
    record.rating = assessment.rating
    record.score_rationale = assessment.score_rationale
    record.transition_rationale = assessment.transition_rationale
    record.model_version = assessment.model_version
    record.weight_set_version = assessment.weight_set_version
    record.transition_policy_version = assessment.transition_policy_version
    record.dimensions = [dimension.model_dump(mode="json") for dimension in assessment.dimensions]
    record.criteria = [criterion.model_dump(mode="json") for criterion in assessment.criteria]
    return record


def assessment_record(
    run_id: UUID,
    assessment: CanonicalAssessment,
    *,
    initiative_id: UUID | None = None,
    evidence_version_id: UUID | None = None,
) -> CanonicalAssessmentDb:
    """Build a complete persistence record for one run."""
    return apply_assessment(
        CanonicalAssessmentDb(
            run_id=run_id,
            initiative_id=initiative_id,
            evidence_version_id=evidence_version_id,
        ),
        assessment,
    )
