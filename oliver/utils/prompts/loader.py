# Path: utils/prompts/loader.py
# Description: Load Oliver's model prompts.

from functools import lru_cache
from typing import Optional

from jinja2 import Environment, PackageLoader, StrictUndefined

_environment = Environment(
    # Locate prompts relative to the utils package without depending on a
    # machine-specific filesystem path.
    loader=PackageLoader("utils", "prompts"),
    # The rendered result is a plain-text model prompt, not an HTML document.
    # Disabling autoescaping preserves characters in the email thread exactly
    # instead of converting them into HTML entities.
    autoescape=False,
    # Raise an error if the template references a variable that was not passed
    # by the caller. This prevents missing values from silently rendering as
    # empty strings inside Oliver's system prompt.
    undefined=StrictUndefined,
    # Remove the first newline after Jinja block tags such as {% if %}. This
    # avoids unwanted blank lines if control blocks are added to the prompt.
    trim_blocks=True,
    # Remove spaces and tabs before Jinja block tags. This keeps template
    # control-flow indentation from leaking into the rendered prompt.
    lstrip_blocks=True,
    # Do not preserve the template file's final newline in the built prompt.
    keep_trailing_newline=False,
)


@lru_cache
def _static_prompt(template_name: str) -> str:
    return _environment.get_template(template_name).render().strip()


def build_system_prompt(email_thread: str, canonical_assessment: Optional[str] = None) -> str:
    """Build the system prompt with the thread and any verified scoring result."""
    return _environment.get_template("system-prompt.jinja2").render(
        canonical_assessment=canonical_assessment,
        email_thread=email_thread,
    )


def assessment_agent_prompt() -> str:
    """Return the Assessment Agent's evidence-interpretation instructions."""
    return _static_prompt("assessment-agent-prompt.jinja2")


def portfolio_agent_prompt() -> str:
    """Return the Portfolio Agent's verified-snapshot instructions."""
    return _static_prompt("portfolio-agent-prompt.jinja2")


def scout_agent_prompt() -> str:
    """Return the Scout Agent's candidate-classification instructions."""
    return _static_prompt("scout-agent-prompt.jinja2")


def coach_request_prompt() -> str:
    """Return the user message that starts a Coach model turn."""
    return _static_prompt("coach-request-prompt.jinja2")
