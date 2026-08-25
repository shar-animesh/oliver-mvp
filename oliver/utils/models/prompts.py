"""Structured response contract for Oliver's final output.

Oliver returns one of three shapes:

- an ``assessment`` reply, whose prose sections are rendered into the branded
  stage-gate report alongside the deterministic canonical score and breakdown;
- a plain ``message`` reply (conversational answer, information request, or
  lifecycle note) delivered as an HTML fragment inside the branded shell; or
- ``NO_REPLY`` when no response is warranted.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

OliverAction = Literal["SEND_EMAIL", "NO_REPLY"]
ReplyKind = Literal["assessment", "message"]


class CoachingItem(BaseModel):
    """One prioritized coaching recommendation."""

    title: str = Field(min_length=3, description="Short bold lead, e.g. 'Quantify the value hypothesis'.")
    detail: str = Field(min_length=10, description="Why it matters and the concrete action to take.")
    example: Optional[str] = Field(default=None, description="Optional short template or worked example the recipient can reuse.")
    criterion_ids: List[str] = Field(
        min_length=1,
        description="Approved transition criterion IDs that authorize and ground this recommendation.",
    )


class ApproachGuidance(BaseModel):
    """Plain-language guidance on the AI technique and first build."""

    problem_type: str = Field(min_length=10, description="What kind of AI problem this is, in plain terms.")
    recommended_approach: str = Field(min_length=10, description="A pragmatic, proportionate approach to prove value early.")
    what_to_do_first: str = Field(min_length=10, description="The smallest concrete first build or experiment.")
    criterion_ids: List[str] = Field(
        min_length=1,
        description="Approved transition criterion IDs grounding this guidance.",
    )


class Opportunity(BaseModel):
    """One prioritized opportunity to strengthen the proposal."""

    area: str = Field(min_length=3, description="The area to strengthen, e.g. 'Value & sponsorship'.")
    priority: Literal["High", "Medium", "Low"]
    suggestion: str = Field(min_length=10, description="The specific, actionable improvement.")
    criterion_ids: List[str] = Field(
        min_length=1,
        description="Approved transition criterion IDs grounding this opportunity.",
    )


class PathForward(BaseModel):
    """The route to the next design-and-innovation gate."""

    timeline: Optional[str] = Field(
        default=None,
        description="A timeline only when supplied by the participant or authenticated policy; otherwise null.",
    )
    milestones: List[str] = Field(default_factory=list, description="Evidence-backed milestones for the transition.")
    criterion_ids: List[str] = Field(min_length=1, description="Approved transition criterion IDs grounding this path.")


class NextStep(BaseModel):
    """One recommended next step with an owner and a timeline."""

    action: str = Field(min_length=5, description="The action to take.")
    owner: Optional[str] = Field(default=None, description="A verified owner only; null when none is supplied.")
    timeline: Optional[str] = Field(
        default=None,
        description="A participant- or policy-supplied timeframe only; null when none is supplied.",
    )
    criterion_ids: List[str] = Field(min_length=1, description="Approved transition criterion IDs grounding this action.")


class AssessmentReport(BaseModel):
    """The prose sections of a detailed initiative assessment.

    The numeric score, DI stage, rating, and the dimension breakdown come from
    the canonical scoring policy, not from these fields.
    """

    position_note: str = Field(min_length=10, description="One-line orientation shown under the transition header.")
    executive_summary: str = Field(min_length=40, description="A concise, proposal-specific overview and the most important next move.")
    working_well: List[str] = Field(default_factory=list, description="Evidence-backed strengths, each tied to a concrete detail.")
    coaching_recommendations: List[CoachingItem] = Field(default_factory=list)
    approach_guidance: Optional[ApproachGuidance] = None
    opportunities: List[Opportunity] = Field(default_factory=list)
    path_forward: Optional[PathForward] = None
    next_steps: List[NextStep] = Field(default_factory=list)
    closing_note: str = Field(min_length=20, description="A brief, warm closing that invites a strengthened resubmission.")


class OliverResponse(BaseModel):
    """Structured response returned by Oliver."""

    action: OliverAction
    reply_kind: Optional[ReplyKind] = None
    subject: Optional[str] = None
    content_html: Optional[str] = None
    report: Optional[AssessmentReport] = None

    @model_validator(mode="after")
    def validate_shape(self) -> "OliverResponse":
        """Require the fields that match the chosen action and reply kind."""
        if self.action == "NO_REPLY":
            if self.subject is not None or self.content_html is not None or self.report is not None or self.reply_kind is not None:
                raise ValueError("NO_REPLY requires reply_kind, subject, content_html, and report to be null")
            return self

        if self.subject is None or not self.subject.strip():
            raise ValueError("subject is required when action is SEND_EMAIL")
        if self.reply_kind is None:
            raise ValueError("reply_kind is required when action is SEND_EMAIL")
        if self.reply_kind == "assessment":
            if self.report is None:
                raise ValueError("report is required when reply_kind is assessment")
            if self.content_html is not None:
                raise ValueError("content_html must be null when reply_kind is assessment")
        else:
            if self.content_html is None or not self.content_html.strip():
                raise ValueError("content_html is required when reply_kind is message")
            if self.report is not None:
                raise ValueError("report must be null when reply_kind is message")
        return self
