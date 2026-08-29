"""Render Oliver's fixed Siemens Energy email shell."""

from importlib.resources import files
from typing import Optional

import bleach
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from utils.models import AssessmentReport
from utils.scoring.models import CanonicalAssessment
from utils.transition_policy.presentation import participant_transition_recommendation, remove_internal_criterion_ids

_PRIORITY_BADGES = {
    "High": ("#FDE7E9", "#B3261E"),
    "Medium": ("#FCEFD6", "#8A5A00"),
    "Low": ("#ECECEC", "#5F5F5F"),
}

_ALLOWED_CONTENT_TAGS = {
    "a",
    "br",
    "em",
    "h2",
    "h3",
    "li",
    "ol",
    "p",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}

# Load the packaged Siemens Energy logo once when this module is imported. The
# source file contains only base64 text; strip() removes its file-ending newline
# before the data-URI prefix is added.
_LOGO_DATA_URI = "data:image/png;base64," + (
    files("utils.templates").joinpath("assets/siemens-energy-logo.png.b64").read_text(encoding="ascii").strip()
)

_environment = Environment(
    # Locate the email templates inside the installed utils Python package.
    # This works both from the repository and from an installed wheel without a
    # machine-specific filesystem path.
    loader=PackageLoader("utils", "templates"),
    # Automatically HTML-escape ordinary values rendered into files ending in
    # .html. This protects values such as subject and preheader from being
    # interpreted as markup.
    autoescape=select_autoescape(enabled_extensions=("html",)),
    # Raise an error if the template references a variable that the caller did
    # not supply, instead of silently rendering the missing value as an empty
    # string.
    undefined=StrictUndefined,
    # Remove the first newline after Jinja block tags such as {% if %}. This
    # prevents template control flow from adding unnecessary blank lines.
    trim_blocks=True,
    # Remove spaces and tabs before Jinja block tags so template indentation
    # does not create unwanted whitespace in the generated HTML.
    lstrip_blocks=True,
    # Do not preserve the template file's final newline in the rendered email.
    keep_trailing_newline=False,
)


def render_oliver_email(
    *,
    subject: str,
    content_html: str,
    preheader: Optional[str] = None,
) -> str:
    """Place the model-generated fragment inside the fixed brand shell."""
    sanitized_content = bleach.clean(
        content_html,
        tags=_ALLOWED_CONTENT_TAGS,
        attributes={"a": ["href", "title"]},
        protocols={"http", "https"},
        strip=True,
        strip_comments=True,
    )
    rendered = _environment.get_template("oliver-email.jinja2.html").render(
        subject=subject.strip(),
        preheader=(preheader or subject).strip(),
        logo_data_uri=_LOGO_DATA_URI,
        # Only the allow-listed fragment is marked safe. All other template
        # values remain subject to Jinja's automatic HTML escaping.
        content_html=Markup(sanitized_content),
    )
    return remove_internal_criterion_ids(rendered)


def render_assessment_email(
    *,
    subject: str,
    report: AssessmentReport,
    assessment: CanonicalAssessment,
    preheader: Optional[str] = None,
) -> str:
    """Render the branded transition report from model prose and canonical policy data."""
    stage = assessment.current_stage
    target_stage = assessment.transition_target
    next_stage = target_stage
    scored_dimension_count = sum(dimension.value is not None for dimension in assessment.dimensions)
    score_display = str(assessment.composite_score) if assessment.composite_score is not None else "Incomplete"
    score_status = (
        f"{scored_dimension_count}/{len(assessment.dimensions)} dimensions scored"
        if assessment.composite_score is None
        else "Complete stage-weighted score"
    )
    weight_note = ", ".join(f"{dimension.agent} {dimension.weight}%" for dimension in assessment.dimensions)
    recommendation = participant_transition_recommendation(assessment)

    rendered = _environment.get_template("oliver-assessment.jinja2.html").render(
        subject=subject.strip(),
        preheader=(preheader or subject).strip(),
        logo_data_uri=_LOGO_DATA_URI,
        stage_code=stage.value,
        stage_name=stage.display_name,
        path_heading=(f"Path to {next_stage.value} — {next_stage.display_name}" if next_stage else "Scale sustainment and value realization"),
        score_display=score_display,
        score_status=score_status,
        rating=assessment.rating,
        gate_outcome=assessment.gate_outcome.value.replace("_", " ").title(),
        recommendation=recommendation,
        weight_note=weight_note,
        position_note=report.position_note,
        executive_summary=report.executive_summary,
        working_well=report.working_well,
        coaching=report.coaching_recommendations,
        approach=report.approach_guidance,
        opportunities=[
            {
                "area": opportunity.area,
                "priority": opportunity.priority,
                "suggestion": opportunity.suggestion,
                "badge_bg": _PRIORITY_BADGES[opportunity.priority][0],
                "badge_fg": _PRIORITY_BADGES[opportunity.priority][1],
            }
            for opportunity in report.opportunities
        ],
        path=report.path_forward,
        next_steps=report.next_steps,
        closing_note=report.closing_note,
        dimensions=[
            {
                "label": dimension.dimension_label,
                "agent": dimension.agent,
                "state": dimension.state.value,
                "value": dimension.value,
                "weight": dimension.weight,
                "summary": dimension.summary,
            }
            for dimension in assessment.dimensions
        ],
    )
    return remove_internal_criterion_ids(rendered)
