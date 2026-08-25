"""Canonical Oliver idea scoring contracts and service."""

from .exceptions import UnassessableEmailError
from .models import CanonicalAssessment, DimensionScore, DIStage, LifecycleState
from .service import assess_email, consolidate_dimensions

__all__ = [
    "CanonicalAssessment",
    "DIStage",
    "DimensionScore",
    "LifecycleState",
    "UnassessableEmailError",
    "assess_email",
    "consolidate_dimensions",
]
