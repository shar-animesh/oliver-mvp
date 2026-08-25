# Path: config.py
# Description: Central validated configuration for the Oliver API, OpenAI models, and PostgreSQL.

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, PositiveInt, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application, model-provider, and database settings."""

    ENV: str = "development"
    LOGGING_LEVEL: str = "INFO"

    OPENAI_API_KEY: SecretStr
    OPENAI_BASE_URL: Optional[str] = None
    OPENAI_MODEL: str
    OPENAI_REASONING_EFFORT: str = "high"
    OPENAI_REQUEST_TIMEOUT_SECONDS: int = Field(default=300, ge=30, le=600)
    OPENAI_MAX_RETRIES: int = Field(default=0, ge=0, le=2)
    OPENAI_EMBEDDING_MODEL: str
    OPENAI_EMBEDDING_DIMENSIONS: PositiveInt
    ASSESSMENT_EVALUATOR_MODE: Literal["llm", "rubric"] = "llm"
    ASSESSMENT_REASONING_EFFORT: str = "medium"
    ASSESSMENT_RESPONSE_RETRIES: int = Field(default=1, ge=0, le=2)
    ASSESSMENT_MAX_EVIDENCE_CHARS: PositiveInt = 120_000

    ATTACHMENT_STORAGE_DIR: str = ".data/attachments"
    ATTACHMENT_STORE: Literal["filesystem", "azure_blob"] = "filesystem"
    AZURE_STORAGE_ACCOUNT_URL: Optional[str] = None
    AZURE_STORAGE_CONTAINER: str = "attachments"
    MAX_ATTACHMENT_BYTES: PositiveInt = 25_000_000
    MAX_ATTACHMENT_UNCOMPRESSED_BYTES: PositiveInt = 100_000_000
    MAX_EXTRACTED_ATTACHMENT_CHARS: PositiveInt = 200_000
    DELIVERY_VISIBILITY_TIMEOUT_SECONDS: int = Field(default=300, ge=30, le=3600)

    INTERNAL_API_KEY: SecretStr
    ADMIN_GATEWAY_API_KEY: SecretStr = SecretStr("")
    ADMIN_AUTH_MODE: Literal["local", "entra"] = "local"
    SERVICE_AUTH_MODE: Literal["local_key", "entra"] = "local_key"
    ADMIN_IDENTITIES: str = ""
    LIFECYCLE_APPROVER_IDENTITIES: str = ""
    ENTRA_TENANT_ID: Optional[str] = None
    ENTRA_API_CLIENT_ID: Optional[str] = None
    ENTRA_ADMIN_READ_ROLES: str = "Oliver.Admin.Read,Oliver.Platform.Admin"
    ENTRA_LIFECYCLE_APPROVER_ROLES: str = "Oliver.Lifecycle.Approve,Oliver.Platform.Admin"
    ENTRA_INSIGHT_OPERATOR_ROLES: str = "Oliver.Assessment.Test,Oliver.Platform.Admin"
    ENTRA_SCOUT_REVIEWER_ROLES: str = "Oliver.Scout.Review,Oliver.Platform.Admin"
    ENTRA_EMAIL_SERVICE_ROLES: str = "Oliver.Service.Email"
    ENTRA_SCHEDULER_SERVICE_ROLES: str = "Oliver.Service.Scheduler"
    ENTRA_SCOUT_SERVICE_ROLES: str = "Oliver.Service.Scout"
    ENTRA_METRICS_SERVICE_ROLES: str = "Oliver.Service.Metrics"
    SCOUT_APPROVED_SOURCE_SYSTEMS: str = ""
    SCOUT_MIN_CONFIDENCE: float = Field(default=0.7, ge=0.0, le=1.0)
    LIFECYCLE_STAGE_SLA_DAYS: str = "DI1:30,DI2:60,DI3:90,DI4:120"
    DATABASE_URL: SecretStr

    @model_validator(mode="after")
    def validate_authentication(self) -> "Settings":
        """Fail closed when user or workload authentication is not usable."""
        if self.ENV == "production" and (self.ADMIN_AUTH_MODE != "entra" or self.SERVICE_AUTH_MODE != "entra"):
            raise ValueError("ADMIN_AUTH_MODE and SERVICE_AUTH_MODE must both be entra when ENV=production")
        if self.ADMIN_AUTH_MODE == "entra" or self.SERVICE_AUTH_MODE == "entra":
            if not self.ENTRA_TENANT_ID or not self.ENTRA_API_CLIENT_ID:
                raise ValueError("ENTRA_TENANT_ID and ENTRA_API_CLIENT_ID are required when Entra authentication is enabled")
        if self.ADMIN_AUTH_MODE == "local":
            configured_key = self.ADMIN_GATEWAY_API_KEY.get_secret_value() or self.INTERNAL_API_KEY.get_secret_value()
            if not configured_key or not self.admin_identities:
                raise ValueError("Local admin authentication requires an API key and at least one ADMIN_IDENTITIES entry")
        if self.SERVICE_AUTH_MODE == "local_key" and not self.INTERNAL_API_KEY.get_secret_value():
            raise ValueError("INTERNAL_API_KEY is required when SERVICE_AUTH_MODE=local_key")
        _ = self.lifecycle_stage_sla_days
        return self

    @property
    def admin_identities(self) -> set[str]:
        """Return normalized administrative identities."""
        return {identity.strip().casefold() for identity in self.ADMIN_IDENTITIES.split(",") if identity.strip()}

    @property
    def lifecycle_approver_identities(self) -> set[str]:
        """Return identities authorized for governed lifecycle decisions."""
        return {identity.strip().casefold() for identity in self.LIFECYCLE_APPROVER_IDENTITIES.split(",") if identity.strip()}

    @property
    def lifecycle_stage_sla_days(self) -> dict[str, int]:
        """Return validated stage cadence limits from one configuration source."""
        stage_sla: dict[str, int] = {}
        for item in self.LIFECYCLE_STAGE_SLA_DAYS.split(","):
            stage, separator, days_text = item.strip().partition(":")
            if not separator or stage not in {"DI1", "DI2", "DI3", "DI4"}:
                raise ValueError(f"Invalid lifecycle SLA entry: {item!r}")
            if stage in stage_sla:
                raise ValueError(f"Lifecycle SLA stage is defined more than once: {stage}")
            try:
                days = int(days_text)
            except ValueError as error:
                raise ValueError(f"Invalid lifecycle SLA entry: {item!r}") from error
            if days < 1:
                raise ValueError(f"Lifecycle SLA must be positive: {item!r}")
            stage_sla[stage] = days
        if set(stage_sla) != {"DI1", "DI2", "DI3", "DI4"}:
            raise ValueError("Lifecycle SLA configuration must define DI1 through DI4 exactly once")
        return stage_sla

    @staticmethod
    def _roles(value: str) -> set[str]:
        return {role.strip() for role in value.split(",") if role.strip()}

    @property
    def entra_admin_read_roles(self) -> set[str]:
        return self._roles(self.ENTRA_ADMIN_READ_ROLES)

    @property
    def entra_lifecycle_approver_roles(self) -> set[str]:
        return self._roles(self.ENTRA_LIFECYCLE_APPROVER_ROLES)

    @property
    def entra_insight_operator_roles(self) -> set[str]:
        return self._roles(self.ENTRA_INSIGHT_OPERATOR_ROLES)

    @property
    def entra_scout_reviewer_roles(self) -> set[str]:
        return self._roles(self.ENTRA_SCOUT_REVIEWER_ROLES)

    @property
    def entra_email_service_roles(self) -> set[str]:
        return self._roles(self.ENTRA_EMAIL_SERVICE_ROLES)

    @property
    def entra_scheduler_service_roles(self) -> set[str]:
        return self._roles(self.ENTRA_SCHEDULER_SERVICE_ROLES)

    @property
    def entra_scout_service_roles(self) -> set[str]:
        return self._roles(self.ENTRA_SCOUT_SERVICE_ROLES)

    @property
    def entra_metrics_service_roles(self) -> set[str]:
        return self._roles(self.ENTRA_METRICS_SERVICE_ROLES)

    @property
    def scout_approved_source_systems(self) -> set[str]:
        return {source.strip().casefold() for source in self.SCOUT_APPROVED_SOURCE_SYSTEMS.split(",") if source.strip()}

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )


@lru_cache
def get_settings() -> Settings:
    """Get settings from .env file."""
    return Settings()
