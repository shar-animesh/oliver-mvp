"""Registrar service for canonical initiatives and immutable evidence versions."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utils.email_content import current_message_text
from utils.postgres import EmailAttachmentDb, EmailMessageDb, EmailThreadDb, EvidenceItemDb, EvidenceVersionDb, EvidenceVersionItemDb, InitiativeDb

_SUBJECT_PREFIX = re.compile(r"^(?:(?:re|fw|fwd)\s*:\s*)+", re.IGNORECASE)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Registrar:
    """Own canonical initiative identity and evidence snapshot creation."""

    def find_initiative(self, database: Session, thread: EmailThreadDb) -> InitiativeDb | None:
        """Return the initiative linked to a thread, when one exists."""
        if thread.initiative_id is None:
            return None
        initiative = database.get(InitiativeDb, thread.initiative_id)
        if initiative is None:
            raise RuntimeError(f"Thread {thread.id} references a missing initiative")
        return initiative

    def ensure_initiative(self, database: Session, thread: EmailThreadDb) -> InitiativeDb:
        """Resolve or create the single initiative linked to an assessed thread."""
        initiative = self.find_initiative(database, thread)
        if initiative is not None:
            return initiative

        title = _SUBJECT_PREFIX.sub("", (thread.subject or "").strip()) or "Untitled initiative"

        # A reply can arrive in a new connector conversation when Graph loses
        # the original conversation ID. If this thread already contains an
        # Oliver response, reuse the matching canonical pilot instead of
        # creating a second initiative with the same subject and owner.
        if thread.participant_email and any(message.direction == "OUTBOUND" for message in thread.messages):
            normalized_title = " ".join(title.split()).casefold()
            candidates = database.scalars(
                select(InitiativeDb).where(InitiativeDb.owner_email == thread.participant_email)
            ).all()
            matching = next(
                (
                    candidate
                    for candidate in sorted(candidates, key=lambda item: (item.updated_at, item.id), reverse=True)
                    if " ".join(candidate.title.split()).casefold() == normalized_title
                ),
                None,
            )
            if matching is not None:
                thread.initiative_id = matching.id
                return matching

        initiative = InitiativeDb(title=title[:200], owner_email=thread.participant_email)
        database.add(initiative)
        database.flush()
        thread.initiative_id = initiative.id
        return initiative

    def capture_message_evidence(
        self,
        database: Session,
        *,
        initiative: InitiativeDb,
        inbound_messages: Sequence[EmailMessageDb],
        attachments: Sequence[EmailAttachmentDb],
        trigger_message: EmailMessageDb,
    ) -> EvidenceVersionDb:
        """Create or reuse an immutable snapshot of all unique inbound evidence."""
        existing_message_ids = set(
            database.scalars(
                select(EvidenceItemDb.message_id).where(
                    EvidenceItemDb.initiative_id == initiative.id,
                    EvidenceItemDb.source_type == "MESSAGE",
                    EvidenceItemDb.message_id.is_not(None),
                )
            )
        )
        for message in inbound_messages:
            if message.id in existing_message_ids:
                continue
            normalized = current_message_text(message.content_html or "")
            if not normalized:
                continue
            database.add(
                EvidenceItemDb(
                    initiative_id=initiative.id,
                    source_type="MESSAGE",
                    message_id=message.id,
                    content_hash=_sha256(normalized),
                )
            )
        existing_attachment_ids = set(
            database.scalars(
                select(EvidenceItemDb.attachment_id).where(
                    EvidenceItemDb.initiative_id == initiative.id,
                    EvidenceItemDb.source_type == "ATTACHMENT",
                    EvidenceItemDb.attachment_id.is_not(None),
                )
            )
        )
        for attachment in attachments:
            if attachment.id in existing_attachment_ids or attachment.blob.extraction_status != "SUCCEEDED":
                continue
            database.add(
                EvidenceItemDb(
                    initiative_id=initiative.id,
                    source_type="ATTACHMENT",
                    attachment_id=attachment.id,
                    content_hash=attachment.blob_hash,
                )
            )
        database.flush()

        items = list(
            database.scalars(
                select(EvidenceItemDb).where(EvidenceItemDb.initiative_id == initiative.id).order_by(EvidenceItemDb.created_at, EvidenceItemDb.id)
            )
        )
        if not items:
            raise RuntimeError(f"Initiative {initiative.id} has no evidence to version")

        fingerprint_source = "\n".join(
            f"{item.source_type}:{item.content_hash}:{item.message_id or item.attachment_id or item.external_source_ref or ''}" for item in items
        )
        fingerprint = _sha256(fingerprint_source)
        existing_version = database.scalar(
            select(EvidenceVersionDb).where(
                EvidenceVersionDb.initiative_id == initiative.id,
                EvidenceVersionDb.source_fingerprint == fingerprint,
            )
        )
        if existing_version is not None:
            return existing_version

        latest_number = database.scalar(select(func.max(EvidenceVersionDb.version)).where(EvidenceVersionDb.initiative_id == initiative.id)) or 0
        evidence_version = EvidenceVersionDb(
            initiative_id=initiative.id,
            version=latest_number + 1,
            source_fingerprint=fingerprint,
            trigger_message_id=trigger_message.id,
        )
        database.add(evidence_version)
        database.flush()
        database.add_all(
            EvidenceVersionItemDb(
                evidence_version_id=evidence_version.id,
                evidence_item_id=item.id,
                initiative_id=initiative.id,
            )
            for item in items
        )
        return evidence_version
