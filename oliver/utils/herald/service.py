"""Herald service for transactional delivery instructions and receipts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from utils.audit import Auditor
from utils.postgres import DeliveryAttemptDb, DeliveryOutboxDb, EmailMessageDb, OliverRunDb


class Herald:
    """Own outbound delivery state without duplicating the email payload."""

    def __init__(self, auditor: Auditor | None = None) -> None:
        self._auditor = auditor or Auditor()

    @staticmethod
    def enqueue(database: Session, *, run: OliverRunDb, outbound_message: EmailMessageDb) -> DeliveryOutboxDb:
        """Add a delivery instruction in the same transaction as its run and message."""
        delivery = DeliveryOutboxDb(run_id=run.id, outbound_message_id=outbound_message.id)
        database.add(delivery)
        return delivery

    @staticmethod
    def for_run(database: Session, run_id: UUID) -> DeliveryOutboxDb | None:
        """Resolve delivery state for an idempotent inbound retry."""
        return database.scalar(select(DeliveryOutboxDb).where(DeliveryOutboxDb.run_id == run_id))

    @staticmethod
    def pending(database: Session, *, limit: int, visibility_timeout_seconds: int) -> list[DeliveryOutboxDb]:
        """Atomically claim due instructions for Logic App polling, oldest first."""
        now = datetime.now(timezone.utc)
        deliveries = list(
            database.scalars(
                select(DeliveryOutboxDb)
                .where(
                    DeliveryOutboxDb.status.in_(("PENDING", "FAILED")),
                    DeliveryOutboxDb.next_attempt_at <= now,
                )
                .options(
                    selectinload(DeliveryOutboxDb.outbound_message),
                    selectinload(DeliveryOutboxDb.run).selectinload(OliverRunDb.thread),
                )
                .order_by(DeliveryOutboxDb.next_attempt_at, DeliveryOutboxDb.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True, of=DeliveryOutboxDb)
            )
        )
        claimed_until = now + timedelta(seconds=visibility_timeout_seconds)
        for delivery in deliveries:
            delivery.next_attempt_at = claimed_until
        database.flush()
        return deliveries

    def record_result(
        self,
        database: Session,
        *,
        delivery_id: UUID,
        idempotency_key: str,
        outcome: str,
        occurred_at: datetime,
        provider_message_id: str | None,
        error: str | None,
    ) -> DeliveryOutboxDb:
        """Record one idempotent send result and update aggregate delivery state."""
        delivery = database.scalar(
            select(DeliveryOutboxDb)
            .where(DeliveryOutboxDb.id == delivery_id)
            .options(selectinload(DeliveryOutboxDb.run).selectinload(OliverRunDb.thread))
            .with_for_update(of=DeliveryOutboxDb)
        )
        if delivery is None:
            raise ValueError("Delivery instruction was not found")
        existing_attempt = database.scalar(select(DeliveryAttemptDb).where(DeliveryAttemptDb.idempotency_key == idempotency_key))
        if existing_attempt is not None:
            if existing_attempt.delivery_id != delivery.id:
                raise ValueError("Idempotency key is already bound to a different delivery instruction")
            existing_delivery = database.get(DeliveryOutboxDb, existing_attempt.delivery_id)
            if existing_delivery is None:
                raise RuntimeError("Delivery attempt references a missing instruction")
            return existing_delivery
        database.add(
            DeliveryAttemptDb(
                delivery_id=delivery.id,
                idempotency_key=idempotency_key,
                outcome=outcome,
                provider_message_id=provider_message_id,
                error=error,
                occurred_at=occurred_at,
            )
        )
        delivery.attempt_count += 1
        if outcome == "SENT":
            delivery.status = "SENT"
            delivery.provider_message_id = provider_message_id or delivery.provider_message_id
            delivery.last_error = None
            delivery.delivered_at = occurred_at
        elif delivery.status != "SENT":
            delivery.status = "FAILED"
            delivery.last_error = (error or "Logic App reported a failed delivery")[:2000]
            delay_seconds = min(3600, 60 * (2 ** min(delivery.attempt_count - 1, 6)))
            delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)

        initiative_id = delivery.run.thread.initiative_id
        self._auditor.record(
            database,
            event_type="EMAIL_DELIVERY_SENT" if outcome == "SENT" else "EMAIL_DELIVERY_FAILED",
            initiative_id=initiative_id,
            actor_type="MANAGED_IDENTITY",
            actor_id="LogicApp",
            subject_type="delivery_outbox",
            subject_id=delivery.id,
            correlation_id=delivery.run_id,
            payload={
                "outcome": outcome,
                "attempt_count": delivery.attempt_count,
                "provider_message_id": provider_message_id,
                "error": error,
            },
        )
        return delivery
