"""HTTP contracts for Sentinel and Realizer services."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class MetricDefinitionRequest(BaseModel):
    """Governed threshold definition created by an authorized reviewer."""

    name: str = Field(min_length=2, max_length=128)
    metric_type: Literal["SLO", "VALUE"]
    unit: str = Field(min_length=1, max_length=64)
    direction: Literal["AT_LEAST", "AT_MOST"]
    threshold: float = Field(allow_inf_nan=False)
    baseline: Optional[float] = Field(default=None, allow_inf_nan=False)
    source_system: str = Field(min_length=2, max_length=128)


class MetricDefinitionResponse(BaseModel):
    """Persisted metric definition."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    initiative_id: UUID
    name: str
    metric_type: str
    unit: str
    direction: str
    threshold: float
    baseline: Optional[float]
    source_system: str
    created_by: str
    created_at: datetime


class MetricObservationRequest(BaseModel):
    """Idempotent source measurement."""

    idempotency_key: str = Field(min_length=1, max_length=512)
    value: float = Field(allow_inf_nan=False)
    source_system: str = Field(min_length=2, max_length=128)
    source_reference: str = Field(min_length=1, max_length=512)
    observed_at: AwareDatetime
    metadata: Optional[dict[str, object]] = None


class MetricObservationResponse(BaseModel):
    """Stored observation and deterministic breach result."""

    id: UUID
    metric_id: UUID
    value: float
    observed_at: datetime
    breached: bool
    alert_id: Optional[UUID]


class ValueRealizationResponse(BaseModel):
    """Latest actual-versus-target result for one value metric."""

    metric_id: UUID
    name: str
    unit: str
    baseline: Optional[float]
    target: float
    actual: Optional[float]
    target_met: Optional[bool]
    progress_percent: Optional[float]
    observed_at: Optional[datetime]
