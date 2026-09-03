"""Governed Scout Agent for approved candidate-source records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from utils.audit import Auditor
from utils.model_provider import parse_structured_output, structured_text_config
from utils.postgres import EvidenceItemDb, EvidenceVersionDb, EvidenceVersionItemDb, InitiativeDb, ScoutCandidateDb
from utils.prompts import scout_agent_prompt


class ScoutSourceRecord(BaseModel):
    """One record supplied by an approved source connector."""

    source_reference: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=20, max_length=20_000)
    owner_hint: str | None = Field(default=None, max_length=320)


class ScoutDiscoveryRequest(BaseModel):
    """Bounded batch from one explicitly allowlisted source system."""

    source_system: str = Field(min_length=2, max_length=128)
    records: list[ScoutSourceRecord] = Field(min_length=1, max_length=25)


class ScoutFinding(BaseModel):
    """Structured Scout judgment for one source record."""

    source_reference: str
    is_candidate: bool
    title: str = Field(min_length=3, max_length=200)
    summary: str = Field(min_length=20, max_length=2000)
    proposed_owner: str | None = Field(default=None, max_length=320)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=20, max_length=1200)


class ScoutFindings(BaseModel):
    """Batch output contract."""

    findings: list[ScoutFinding]


@dataclass(frozen=True)
class ScoutAgentResult:
    """New and already-known candidates produced by one discovery call."""

    candidates: tuple[ScoutCandidateDb, ...]
    created_count: int


class ScoutAgent:
    """Classify approved-source records into a deduplicated review queue."""

    def __init__(
        self,
        *,
        client: OpenAI,
        model: str,
        reasoning_effort: str,
        approved_sources: set[str],
        minimum_confidence: float,
        auditor: Auditor | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._approved_sources = approved_sources
        self._minimum_confidence = minimum_confidence
        self._auditor = auditor or Auditor()

    def discover(self, database: Session, *, request: ScoutDiscoveryRequest, actor_id: str) -> ScoutAgentResult:
        source_system = request.source_system.strip().casefold()
        if source_system not in self._approved_sources:
            raise ValueError(f"Scout source {request.source_system!r} is not approved")
        source_payload = {
            "source_system": source_system,
            "records": [record.model_dump() for record in request.records],
        }
        response = self._client.responses.create(
            model=self._model,
            instructions=scout_agent_prompt(),
            input=[{"role": "user", "content": json.dumps(source_payload, sort_keys=True)}],
            text=structured_text_config(ScoutFindings),
            reasoning={"effort": self._reasoning_effort},
            store=False,
        )
        output = parse_structured_output(response, ScoutFindings)
        records_by_reference = {record.source_reference: record for record in request.records}
        if len(records_by_reference) != len(request.records):
            raise ValueError("Scout source references must be unique within a batch")
        finding_references = [finding.source_reference for finding in output.findings]
        if len(finding_references) != len(set(finding_references)) or set(finding_references) != set(records_by_reference):
            raise RuntimeError("Scout Agent did not return exactly one finding for each source record")

        candidates: list[ScoutCandidateDb] = []
        created_count = 0
        for finding in output.findings:
            if not finding.is_candidate or finding.confidence < self._minimum_confidence:
                continue
            source_record = records_by_reference[finding.source_reference]
            content_hash = hashlib.sha256(source_record.content.strip().encode("utf-8")).hexdigest()
            candidate = database.scalar(
                select(ScoutCandidateDb).where(
                    ScoutCandidateDb.source_system == source_system,
                    ScoutCandidateDb.source_reference == finding.source_reference,
                    ScoutCandidateDb.content_hash == content_hash,
                )
            )
            if candidate is None:
                candidate = ScoutCandidateDb(
                    source_system=source_system,
                    source_reference=finding.source_reference,
                    content_hash=content_hash,
                    title=finding.title,
                    summary=finding.summary,
                    proposed_owner=finding.proposed_owner or source_record.owner_hint,
                    confidence=finding.confidence,
                    rationale=finding.rationale,
                )
                database.add(candidate)
                database.flush()
                created_count += 1
                self._auditor.record(
                    database,
                    event_type="SCOUT_CANDIDATE_DISCOVERED",
                    actor_type="MANAGED_IDENTITY",
                    actor_id=actor_id,
                    subject_type="scout_candidate",
                    subject_id=candidate.id,
                    payload={
                        "source_system": source_system,
                        "source_reference": finding.source_reference,
                        "confidence": finding.confidence,
                    },
                )
            candidates.append(candidate)
        return ScoutAgentResult(candidates=tuple(candidates), created_count=created_count)


class ScoutWorkflow:
    """Human-governed promotion and dismissal of Scout candidates."""

    def __init__(self, auditor: Auditor | None = None) -> None:
        self._auditor = auditor or Auditor()

    def promote(self, database: Session, *, candidate_id: UUID, actor_id: str) -> tuple[ScoutCandidateDb, InitiativeDb]:
        candidate = database.scalar(select(ScoutCandidateDb).where(ScoutCandidateDb.id == candidate_id).with_for_update())
        if candidate is None:
            raise ValueError("Scout candidate was not found")
        if candidate.status == "PROMOTED" and candidate.promoted_initiative_id is not None:
            initiative = database.get(InitiativeDb, candidate.promoted_initiative_id)
            if initiative is None:
                raise RuntimeError("Promoted Scout candidate references a missing initiative")
            return candidate, initiative
        if candidate.status == "DISMISSED":
            raise ValueError("A dismissed Scout candidate cannot be promoted")

        initiative = InitiativeDb(
            title=candidate.title,
            owner_email=candidate.proposed_owner,
            lifecycle_state="Discovered",
        )
        database.add(initiative)
        database.flush()
        evidence_item = EvidenceItemDb(
            initiative_id=initiative.id,
            source_type="SCOUT",
            external_source_ref=f"scout-candidate:{candidate.id}",
            content_hash=candidate.content_hash,
        )
        database.add(evidence_item)
        database.flush()
        evidence_version = EvidenceVersionDb(
            initiative_id=initiative.id,
            version=1,
            source_fingerprint=candidate.content_hash,
        )
        database.add(evidence_version)
        database.flush()
        database.add(
            EvidenceVersionItemDb(
                evidence_version_id=evidence_version.id,
                evidence_item_id=evidence_item.id,
                initiative_id=initiative.id,
            )
        )

        candidate.status = "PROMOTED"
        candidate.promoted_initiative_id = initiative.id
        candidate.reviewed_by = actor_id
        candidate.reviewed_at = datetime.now(timezone.utc)
        self._auditor.record(
            database,
            event_type="SCOUT_CANDIDATE_PROMOTED",
            initiative_id=initiative.id,
            actor_type="USER",
            actor_id=actor_id,
            subject_type="scout_candidate",
            subject_id=candidate.id,
            payload={"source_system": candidate.source_system, "source_reference": candidate.source_reference},
        )
        return candidate, initiative

    def dismiss(self, database: Session, *, candidate_id: UUID, actor_id: str, reason: str) -> ScoutCandidateDb:
        candidate = database.scalar(select(ScoutCandidateDb).where(ScoutCandidateDb.id == candidate_id).with_for_update())
        if candidate is None:
            raise ValueError("Scout candidate was not found")
        if candidate.status == "PROMOTED":
            raise ValueError("A promoted Scout candidate cannot be dismissed")
        candidate.status = "DISMISSED"
        candidate.reviewed_by = actor_id
        candidate.reviewed_at = datetime.now(timezone.utc)
        self._auditor.record(
            database,
            event_type="SCOUT_CANDIDATE_DISMISSED",
            actor_type="USER",
            actor_id=actor_id,
            subject_type="scout_candidate",
            subject_id=candidate.id,
            payload={"reason": reason},
        )
        return candidate
