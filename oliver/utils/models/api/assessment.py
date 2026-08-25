"""Role-governed, non-persistent assessment-lab contracts."""

from typing import Optional

from pydantic import BaseModel, Field

from utils.models.prompts import OliverAction, ReplyKind
from utils.scoring import CanonicalAssessment, DIStage


class AssessmentTestRequest(BaseModel):
    """Evidence supplied for a sandbox assessment that cannot change lifecycle state."""

    subject: str = Field(min_length=3, max_length=200)
    evidence: str = Field(min_length=20, max_length=120_000)
    current_stage: DIStage = DIStage.DI1


class AssessmentTestResult(CanonicalAssessment):
    """Canonical sandbox result plus the complete non-persistent Coach email preview."""

    response_action: OliverAction
    response_kind: Optional[ReplyKind] = None
    email_subject: Optional[str] = None
    email_html: Optional[str] = None
