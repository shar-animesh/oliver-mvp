"""Oliver service-to-service security dependencies."""

from .admin import AdminPrincipal, require_admin_identity, require_insight_operator, require_lifecycle_approver, require_scout_reviewer
from .internal import require_internal_api_key
from .service import require_email_service, require_metrics_service, require_scheduler_service, require_scout_service

__all__ = [
    "AdminPrincipal",
    "require_admin_identity",
    "require_email_service",
    "require_internal_api_key",
    "require_insight_operator",
    "require_lifecycle_approver",
    "require_metrics_service",
    "require_scheduler_service",
    "require_scout_reviewer",
    "require_scout_service",
]
