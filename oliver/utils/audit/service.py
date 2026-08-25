"""Application service for recording immutable audit events."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from utils.postgres import AuditEventDb


class Auditor:
    """Append a material event to Oliver's protected audit ledger."""

    def record(
        self,
        database: Session,
        *,
        event_type: str,
        subject_type: str,
        subject_id: str | UUID,
        initiative_id: UUID | None = None,
        actor_type: str = "SYSTEM",
        actor_id: str = "Oliver",
        correlation_id: str | UUID | None = None,
        payload: dict[str, object] | None = None,
    ) -> AuditEventDb:
        event = AuditEventDb(
            initiative_id=initiative_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            subject_type=subject_type,
            subject_id=str(subject_id),
            correlation_id=str(correlation_id) if correlation_id is not None else None,
            payload=payload or {},
        )
        database.add(event)
        return event
