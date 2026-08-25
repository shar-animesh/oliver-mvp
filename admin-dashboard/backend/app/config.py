# Path: app/config.py
# Description: Central, validated environment configuration for the admin dashboard backend.

from functools import lru_cache
from typing import Dict, List, Literal, Optional, Set

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from process environment and an optional local `.env` file."""

    # Application configuration
    ENV: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    ANYIO_THREAD_POOL_TOKENS: int = Field(default=200, ge=1)
    OLIVER_CORS_ORIGINS: str = "http://localhost:5173"
    DATABASE_URL: SecretStr
    ADMIN_AUTH_MODE: Literal["local", "entra"] = "local"
    ADMIN_SESSION_SECRET: SecretStr
    ADMIN_SESSION_TTL_SECONDS: int = Field(default=28_800, ge=300, le=86_400)
    ADMIN_LOCAL_USER_HASHES: SecretStr = SecretStr("")
    ADMIN_LOCAL_ROLES: str = "Oliver.Admin.Read,Oliver.Assessment.Test"
    OLIVER_API_URL: str = "http://localhost:8001"
    OLIVER_INTERNAL_API_KEY: SecretStr = SecretStr("")
    OLIVER_REQUEST_TIMEOUT_SECONDS: int = Field(default=660, ge=60, le=1_300)
    ENTRA_TENANT_ID: Optional[str] = None
    ENTRA_CLIENT_ID: Optional[str] = None
    ENTRA_REQUIRED_SCOPE: str = "access_as_user"
    ENTRA_ADMIN_READ_ROLES: str = "Oliver.Admin.Read,Oliver.Platform.Admin"

    @model_validator(mode="after")
    def validate_authentication(self) -> "Settings":
        """Reject unusable or unsafe authentication configurations at startup."""
        if self.ENV == "production" and self.ADMIN_AUTH_MODE != "entra":
            raise ValueError("ADMIN_AUTH_MODE must be entra when ENV=production")
        if self.ADMIN_AUTH_MODE == "entra":
            if not self.ENTRA_TENANT_ID or not self.ENTRA_CLIENT_ID:
                raise ValueError("ENTRA_TENANT_ID and ENTRA_CLIENT_ID are required when ADMIN_AUTH_MODE=entra")
            if not self.entra_admin_read_roles:
                raise ValueError("ENTRA_ADMIN_READ_ROLES must define at least one role when ADMIN_AUTH_MODE=entra")
            if not self.ENTRA_REQUIRED_SCOPE.strip():
                raise ValueError("ENTRA_REQUIRED_SCOPE is required when ADMIN_AUTH_MODE=entra")
        else:
            if not self.local_user_hashes:
                raise ValueError("ADMIN_LOCAL_USER_HASHES must define at least one user when ADMIN_AUTH_MODE=local")
            if not self.OLIVER_INTERNAL_API_KEY.get_secret_value().strip():
                raise ValueError("OLIVER_INTERNAL_API_KEY is required when ADMIN_AUTH_MODE=local")
        return self

    @property
    def cors_origins(self) -> List[str]:
        """Return normalized browser origins from the comma-separated environment value."""
        return [origin.strip() for origin in self.OLIVER_CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def local_user_hashes(self) -> Dict[str, str]:
        """Parse the local username-to-password-hash allowlist."""
        entries: Dict[str, str] = {}
        for item in self.ADMIN_LOCAL_USER_HASHES.get_secret_value().split(","):
            username, separator, password_hash = item.strip().partition(":")
            if separator and username and password_hash:
                entries[username.casefold()] = password_hash
        return entries

    @property
    def entra_admin_read_roles(self) -> Set[str]:
        """Return application roles that permit dashboard access."""
        return {role.strip() for role in self.ENTRA_ADMIN_READ_ROLES.split(",") if role.strip()}

    @property
    def local_roles(self) -> Set[str]:
        """Return localhost-only roles granted to every configured local test admin."""
        return {role.strip() for role in self.ADMIN_LOCAL_ROLES.split(",") if role.strip()}

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings singleton."""
    return Settings()
