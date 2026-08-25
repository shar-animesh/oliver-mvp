"""Deterministic operational threshold and realized-value services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from utils.audit import Auditor
from utils.lifecycle import LifecycleConflictError
from utils.postgres import InitiativeDb, MetricDefinitionDb, MetricObservationDb, OperationalAlertDb


def threshold_breached(*, value: float, threshold: float, direction: str) -> bool:
    """Return whether a measured value violates its governed threshold."""
    if direction == "AT_LEAST":
        return value < threshold
    if direction == "AT_MOST":
        return value > threshold
    raise ValueError(f"Unsupported metric direction {direction}")


@dataclass(frozen=True)
class ValueRealization:
    """Latest actual-versus-target result for one value metric."""

    metric_id: UUID
    name: str
    unit: str
    baseline: float | None
    target: float
    actual: float | None
    target_met: bool | None
    progress_percent: float | None
    observed_at: datetime | None


class Sentinel:
    """Store governed metrics and emit one alert per breaching observation."""

    def __init__(self, auditor: Auditor | None = None) -> None:
        self._auditor = auditor or Auditor()

    def define_metric(
        self,
        database: Session,
        *,
        initiative_id: UUID,
        name: str,
        metric_type: str,
        unit: str,
        direction: str,
        threshold: float,
        baseline: float | None,
        source_system: str,
        actor_id: str,
    ) -> MetricDefinitionDb:
        initiative = database.get(InitiativeDb, initiative_id)
        if initiative is None:
            raise ValueError("Initiative was not found")
        if initiative.current_stage not in {"DI3", "DI4", "DI5"}:
            raise ValueError("Operational and value metrics can be defined from DI3 onward")
        normalized_name = name.strip()
        normalized_unit = unit.strip()
        normalized_source = source_system.casefold()
        existing = database.scalar(
            select(MetricDefinitionDb).where(
                MetricDefinitionDb.initiative_id == initiative_id,
                MetricDefinitionDb.name == normalized_name,
            )
        )
        if existing is not None:
            expected = (metric_type, normalized_unit, direction, threshold, baseline, normalized_source)
            actual = (
                existing.metric_type,
                existing.unit,
                existing.direction,
                existing.threshold,
                existing.baseline,
                existing.source_system,
            )
            if actual != expected:
                raise ValueError("A metric with this name already exists with a different definition")
            return existing
        metric = MetricDefinitionDb(
            initiative_id=initiative_id,
            name=normalized_name,
            metric_type=metric_type,
            unit=normalized_unit,
            direction=direction,
            threshold=threshold,
            baseline=baseline,
            source_system=normalized_source,
            created_by=actor_id,
        )
        database.add(metric)
        database.flush()
        self._auditor.record(
            database,
            event_type="METRIC_DEFINED",
            initiative_id=initiative_id,
            actor_type="USER",
            actor_id=actor_id,
            subject_type="metric_definition",
            subject_id=metric.id,
            payload={
                "name": metric.name,
                "metric_type": metric.metric_type,
                "unit": metric.unit,
                "direction": metric.direction,
                "threshold": metric.threshold,
                "baseline": metric.baseline,
                "source_system": metric.source_system,
            },
        )
        return metric

    def record_observation(
        self,
        database: Session,
        *,
        metric_id: UUID,
        idempotency_key: str,
        value: float,
        source_system: str,
        source_reference: str,
        observed_at: datetime,
        metadata: dict[str, object] | None,
        actor_id: str,
    ) -> tuple[MetricObservationDb, OperationalAlertDb | None]:
        normalized_source_system = source_system.casefold()
        existing = database.scalar(select(MetricObservationDb).where(MetricObservationDb.idempotency_key == idempotency_key))
        if existing is not None:
            same_payload = (
                existing.metric_id == metric_id
                and existing.value == value
                and existing.source_reference == source_reference
                and existing.observed_at == observed_at
                and existing.measurement_metadata == metadata
                and existing.metric.source_system == normalized_source_system
            )
            if not same_payload:
                raise ValueError("Idempotency key was already used for a different observation payload")
            return existing, existing.alert
        metric = database.get(MetricDefinitionDb, metric_id)
        if metric is None:
            raise ValueError("Metric definition was not found")
        if metric.source_system != normalized_source_system:
            raise ValueError("Observation source does not match the governed metric definition")
        observation = MetricObservationDb(
            metric_id=metric.id,
            idempotency_key=idempotency_key,
            value=value,
            source_reference=source_reference,
            observed_at=observed_at,
            measurement_metadata=metadata,
        )
        database.add(observation)
        database.flush()
        alert = None
        breached = threshold_breached(value=value, threshold=metric.threshold, direction=metric.direction)
        if breached and metric.metric_type == "SLO":
            alert = OperationalAlertDb(
                initiative_id=metric.initiative_id,
                observation_id=observation.id,
                message=(
                    f"{metric.name} measured {value:g} {metric.unit}; governed threshold is "
                    f"{metric.direction.lower().replace('_', ' ')} {metric.threshold:g} {metric.unit}."
                ),
            )
            database.add(alert)
            initiative = database.get(InitiativeDb, metric.initiative_id)
            if initiative is not None and not initiative.is_on_hold and initiative.lifecycle_state not in {"NoGo", "Retired"}:
                expected_version = initiative.version
                result = database.execute(
                    update(InitiativeDb)
                    .where(InitiativeDb.id == initiative.id, InitiativeDb.version == expected_version)
                    .values(lifecycle_state="Drifted", version=expected_version + 1)
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    raise LifecycleConflictError(f"Initiative {initiative.id} changed while recording the SLO breach")
                database.expire(initiative, ["lifecycle_state", "version"])
        self._auditor.record(
            database,
            event_type="SLO_BREACHED" if alert is not None else "METRIC_OBSERVED",
            initiative_id=metric.initiative_id,
            actor_type="MANAGED_IDENTITY",
            actor_id=actor_id,
            subject_type="metric_observation",
            subject_id=observation.id,
            payload={
                "metric_id": str(metric.id),
                "metric_type": metric.metric_type,
                "value": value,
                "unit": metric.unit,
                "threshold": metric.threshold,
                "breached": breached,
            },
        )
        return observation, alert


class Realizer:
    """Reconcile latest measured value against each governed value target."""

    @staticmethod
    def summarize(database: Session, *, initiative_id: UUID) -> list[ValueRealization]:
        metrics = list(
            database.scalars(
                select(MetricDefinitionDb).where(
                    MetricDefinitionDb.initiative_id == initiative_id,
                    MetricDefinitionDb.metric_type == "VALUE",
                )
            )
        )
        results: list[ValueRealization] = []
        for metric in metrics:
            observation = database.scalar(
                select(MetricObservationDb)
                .where(MetricObservationDb.metric_id == metric.id)
                .order_by(MetricObservationDb.observed_at.desc())
                .limit(1)
            )
            actual = observation.value if observation is not None else None
            target_met = (
                None
                if actual is None
                else not threshold_breached(
                    value=actual,
                    threshold=metric.threshold,
                    direction=metric.direction,
                )
            )
            progress = Realizer._progress(metric, actual)
            results.append(
                ValueRealization(
                    metric_id=metric.id,
                    name=metric.name,
                    unit=metric.unit,
                    baseline=metric.baseline,
                    target=metric.threshold,
                    actual=actual,
                    target_met=target_met,
                    progress_percent=progress,
                    observed_at=observation.observed_at if observation is not None else None,
                )
            )
        return results

    @staticmethod
    def _progress(metric: MetricDefinitionDb, actual: float | None) -> float | None:
        if actual is None or metric.baseline is None or metric.baseline == metric.threshold:
            return None
        if metric.direction == "AT_LEAST":
            raw = (actual - metric.baseline) / (metric.threshold - metric.baseline)
        else:
            raw = (metric.baseline - actual) / (metric.baseline - metric.threshold)
        return round(max(0.0, raw) * 100, 1)
