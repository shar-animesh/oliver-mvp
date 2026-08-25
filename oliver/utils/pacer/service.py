"""Pacer computes time-to-gate and emits each stall event once."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from utils.audit import Auditor
from utils.postgres import InitiativeDb


@dataclass(frozen=True)
class CadenceSnapshot:
    """Deterministic cadence state for one initiative."""

    initiative_id: UUID
    stage: str
    days_in_stage: int
    sla_days: int | None
    days_to_next_gate: int | None
    stall_flag: bool
    on_hold: bool


def cadence_for(
    initiative: InitiativeDb,
    *,
    now: datetime,
    stage_sla_days: dict[str, int],
) -> CadenceSnapshot:
    """Calculate cadence without mutating lifecycle state."""
    days_in_stage = max(0, (now - initiative.stage_entered_at).days)
    sla_days = stage_sla_days.get(initiative.current_stage)
    is_terminal = initiative.current_stage == "DI5" or initiative.lifecycle_state in {"NoGo", "Retired"}
    stall_flag = bool(not initiative.is_on_hold and not is_terminal and sla_days is not None and days_in_stage >= sla_days)
    return CadenceSnapshot(
        initiative_id=initiative.id,
        stage=initiative.current_stage,
        days_in_stage=days_in_stage,
        sla_days=sla_days,
        days_to_next_gate=max(0, sla_days - days_in_stage) if sla_days is not None and not is_terminal else None,
        stall_flag=stall_flag,
        on_hold=initiative.is_on_hold,
    )


class Pacer:
    """Evaluate every initiative and persist newly detected stalls."""

    def __init__(self, *, stage_sla_days: dict[str, int], auditor: Auditor | None = None) -> None:
        self._stage_sla_days = stage_sla_days
        self._auditor = auditor or Auditor()

    def evaluate_all(self, database: Session, *, now: datetime | None = None) -> list[CadenceSnapshot]:
        """Evaluate current cadence and emit idempotent stall events."""
        evaluated_at = now or datetime.now(timezone.utc)
        initiatives = list(database.scalars(select(InitiativeDb).order_by(InitiativeDb.created_at)))
        snapshots: list[CadenceSnapshot] = []
        for initiative in initiatives:
            snapshot = cadence_for(initiative, now=evaluated_at, stage_sla_days=self._stage_sla_days)
            snapshots.append(snapshot)
            if not snapshot.stall_flag or initiative.lifecycle_state == "Stalled":
                continue
            expected_version = initiative.version
            result = database.execute(
                update(InitiativeDb)
                .where(InitiativeDb.id == initiative.id, InitiativeDb.version == expected_version)
                .values(lifecycle_state="Stalled", version=expected_version + 1)
            )
            if result.rowcount != 1:
                continue
            self._auditor.record(
                database,
                event_type="INITIATIVE_STALLED",
                initiative_id=initiative.id,
                actor_id="Pacer",
                subject_type="initiative",
                subject_id=initiative.id,
                payload={
                    "stage": snapshot.stage,
                    "days_in_stage": snapshot.days_in_stage,
                    "sla_days": snapshot.sla_days,
                },
            )
        return snapshots
