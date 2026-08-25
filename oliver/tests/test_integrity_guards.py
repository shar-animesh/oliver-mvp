"""Regression tests for configuration, outbox, and evidence integrity guards."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from config import Settings
from utils.herald import Herald
from utils.postgres import EvidenceVersionItemDb, InitiativeDb


def _settings_values() -> dict[str, object]:
    return {
        "OPENAI_API_KEY": "test-key",
        "OPENAI_MODEL": "test-model",
        "OPENAI_EMBEDDING_MODEL": "test-embedding",
        "OPENAI_EMBEDDING_DIMENSIONS": 1536,
        "INTERNAL_API_KEY": "local-key",
        "ADMIN_IDENTITIES": "admin",
        "DATABASE_URL": "postgresql://test",
    }


class ConfigurationGuardTests(unittest.TestCase):
    def test_production_rejects_local_authentication_modes(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, ENV="production", **_settings_values())

    def test_duplicate_lifecycle_sla_stage_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                LIFECYCLE_STAGE_SLA_DAYS="DI1:30,DI1:45,DI2:60,DI3:90,DI4:120",
                **_settings_values(),
            )

    def test_non_numeric_lifecycle_sla_is_rejected_at_startup(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                LIFECYCLE_STAGE_SLA_DAYS="DI1:thirty,DI2:60,DI3:90,DI4:120",
                **_settings_values(),
            )


class _PendingDatabase:
    def __init__(self, deliveries: list[SimpleNamespace]) -> None:
        self.deliveries = deliveries
        self.statement = None
        self.flushed = False

    def scalars(self, statement):
        self.statement = statement
        return self.deliveries

    def flush(self) -> None:
        self.flushed = True


class DeliveryClaimTests(unittest.TestCase):
    def test_pending_delivery_query_locks_and_claims_rows(self) -> None:
        original_attempt = datetime.now(timezone.utc) - timedelta(minutes=1)
        delivery = SimpleNamespace(next_attempt_at=original_attempt)
        database = _PendingDatabase([delivery])

        result = Herald.pending(database, limit=10, visibility_timeout_seconds=300)

        statement = str(database.statement.compile(dialect=postgresql.dialect()))
        self.assertIn("FOR UPDATE OF delivery_outbox SKIP LOCKED", statement)
        self.assertGreater(delivery.next_attempt_at, original_attempt)
        self.assertTrue(database.flushed)
        self.assertEqual(result, [delivery])

    def test_replayed_idempotency_key_cannot_target_another_delivery(self) -> None:
        delivery = SimpleNamespace(id=uuid4())
        existing_attempt = SimpleNamespace(delivery_id=uuid4())

        class ReplayDatabase:
            def __init__(self) -> None:
                self.results = iter((delivery, existing_attempt))

            def scalar(self, _statement):
                return next(self.results)

        with self.assertRaisesRegex(ValueError, "different delivery instruction"):
            Herald().record_result(
                ReplayDatabase(),  # type: ignore[arg-type]
                delivery_id=delivery.id,
                idempotency_key="already-used",
                outcome="SENT",
                occurred_at=datetime.now(timezone.utc),
                provider_message_id="provider-1",
                error=None,
            )


class EvidenceConstraintTests(unittest.TestCase):
    def test_membership_foreign_keys_include_initiative_identity(self) -> None:
        constrained_columns = {frozenset(constraint.column_keys) for constraint in EvidenceVersionItemDb.__table__.foreign_key_constraints}
        self.assertEqual(
            constrained_columns,
            {
                frozenset({"evidence_version_id", "initiative_id"}),
                frozenset({"evidence_item_id", "initiative_id"}),
            },
        )

    def test_related_idea_sharing_is_explicit_and_private_by_default(self) -> None:
        constraint_names = {constraint.name for constraint in InitiativeDb.__table__.constraints}
        self.assertIn("ck_initiative_related_idea_sharing_scope", constraint_names)
        self.assertEqual(InitiativeDb.__table__.c.related_idea_sharing_scope.default.arg, "PRIVATE")
        self.assertEqual(InitiativeDb.__table__.c.related_idea_sharing_scope.server_default.arg, "PRIVATE")


if __name__ == "__main__":
    unittest.main()
