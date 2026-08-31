"""Portfolio Intelligence Agent over verified aggregate data only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utils.audit import Auditor
from utils.model_provider import parse_structured_output, structured_text_config
from utils.postgres import CanonicalAssessmentDb, InitiativeDb, LifecycleTransitionDb, PortfolioInsightReportDb


class PortfolioPattern(BaseModel):
    """One cross-initiative pattern tied to explicit initiative IDs."""

    title: str = Field(min_length=5, max_length=120)
    finding: str = Field(min_length=20, max_length=400)
    supporting_initiative_ids: list[UUID] = Field(min_length=1)
    evidence_count: int = Field(ge=1)
    category: Literal["EVIDENCE", "EXECUTION", "TECHNICAL", "GOVERNANCE", "SAFETY", "DUPLICATE", "PORTFOLIO"] = "PORTFOLIO"
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    why_it_matters: str = Field(default="", max_length=220)
    recommended_action: str = Field(default="", max_length=220)


class PortfolioInsightReport(BaseModel):
    """Structured management interpretation without invented portfolio facts."""

    executive_summary: str = Field(min_length=40, max_length=2000)
    patterns: list[PortfolioPattern] = Field(default_factory=list, max_length=10)
    recurring_blockers: list[PortfolioPattern] = Field(default_factory=list, max_length=10)
    possible_duplicates: list[PortfolioPattern] = Field(default_factory=list, max_length=10)
    recommendations: list[str] = Field(default_factory=list, max_length=10)


@dataclass(frozen=True)
class PortfolioAgentResult:
    """Persisted report and cache provenance."""

    record: PortfolioInsightReportDb
    report: PortfolioInsightReport
    reused: bool


_INSTRUCTIONS = """
You are Oliver's Portfolio Intelligence Agent. Analyze only the supplied verified JSON snapshot.
Do not infer facts, financial values, delivery status, business units, or relationships that are not present.
Every pattern, blocker, and duplicate group must cite the exact initiative IDs that support it.
Set evidence_count to the number of distinct supporting_initiative_ids. Do not treat similar stages alone as duplication.
Use plain language for an operations administrator. Return 4-6 high-value signals, not a catalogue.
UUIDs may appear only in supporting_initiative_ids. Never place UUIDs or UUID fragments in any prose field.
Never expose raw enum values. Translate HOLD_FOR_EVIDENCE to "more evidence required", CONDITIONAL_ADVANCE
to "ready to advance with conditions", and ADVANCE to "ready to advance".
Refer to pilots by their supplied titles. Explain DI stages as Concept, Pilot, Test, Implement, or Scale when needed.
Every signal must include:
- category (EVIDENCE, EXECUTION, TECHNICAL, GOVERNANCE, SAFETY, DUPLICATE, or PORTFOLIO)
- priority (HIGH only when the snapshot shows a material safety, compliance, delivery, or duplicate risk)
- a concrete finding of at most two short sentences using counts, dimensions, stages, titles, or metrics from the snapshot
- why_it_matters: one short sentence explaining the operational consequence
- recommended_action: one specific, verifiable next step for an administrator
Avoid generic advice such as "review the initiatives". Recommendations must be actions justified by the snapshot, not lifecycle decisions.
Do not instruct the administrator to apply the most advanced gate outcome, merge or delete records, or place a formal hold.
Flag conflicting evidence or decisions for governed human resolution instead.
""".strip()
_REPORT_CONTRACT_VERSION = "2026-08-31-admin-brief-v3"


class PortfolioIntelligenceAgent:
    """Interpret many initiatives while leaving exact metrics to SQL and policy code."""

    def __init__(self, *, client: OpenAI, model: str, reasoning_effort: str, auditor: Auditor | None = None) -> None:
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._auditor = auditor or Auditor()

    def generate(self, database: Session, *, actor_id: str) -> PortfolioAgentResult:
        snapshot = self._snapshot(database)
        if not snapshot["initiatives"]:
            raise ValueError("Portfolio has no canonical initiatives to analyze")
        serialized = json.dumps(
            {"contract_version": _REPORT_CONTRACT_VERSION, "snapshot": snapshot},
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        existing = database.scalar(select(PortfolioInsightReportDb).where(PortfolioInsightReportDb.input_fingerprint == fingerprint))
        if existing is not None:
            return PortfolioAgentResult(
                record=existing,
                report=PortfolioInsightReport.model_validate(existing.report),
                reused=True,
            )

        response = self._client.responses.create(
            model=self._model,
            instructions=_INSTRUCTIONS,
            input=[{"role": "user", "content": serialized}],
            text=structured_text_config(PortfolioInsightReport),
            reasoning={"effort": self._reasoning_effort},
            store=False,
        )
        report = parse_structured_output(response, PortfolioInsightReport)
        self._validate_citations(report, {UUID(item["id"]) for item in snapshot["initiatives"]})
        record = PortfolioInsightReportDb(
            input_fingerprint=fingerprint,
            input_snapshot=snapshot,
            report=report.model_dump(mode="json"),
            model_name=self._model,
            prompt_tokens=response.usage.input_tokens if response.usage is not None else None,
            completion_tokens=response.usage.output_tokens if response.usage is not None else None,
            generated_by=actor_id,
        )
        database.add(record)
        database.flush()
        self._auditor.record(
            database,
            event_type="PORTFOLIO_INSIGHT_GENERATED",
            actor_type="USER",
            actor_id=actor_id,
            subject_type="portfolio_insight_report",
            subject_id=record.id,
            payload={"input_fingerprint": fingerprint, "initiative_count": len(snapshot["initiatives"])},
        )
        return PortfolioAgentResult(record=record, report=report, reused=False)

    @staticmethod
    def _validate_citations(report: PortfolioInsightReport, valid_ids: set[UUID]) -> None:
        for item in [*report.patterns, *report.recurring_blockers, *report.possible_duplicates]:
            cited = set(item.supporting_initiative_ids)
            if not cited.issubset(valid_ids) or item.evidence_count != len(cited):
                raise RuntimeError("Portfolio report contains invalid initiative citations")

    @staticmethod
    def _snapshot(database: Session) -> dict[str, object]:
        initiatives = list(database.scalars(select(InitiativeDb).order_by(InitiativeDb.id)))
        ranked_assessments = (
            select(
                # Canonical assessments use the associated Oliver run as their
                # primary key; there is no separate ``id`` column.
                CanonicalAssessmentDb.run_id.label("assessment_id"),
                func.row_number()
                .over(
                    partition_by=CanonicalAssessmentDb.initiative_id,
                    order_by=(CanonicalAssessmentDb.created_at.desc(), CanonicalAssessmentDb.run_id.desc()),
                )
                .label("row_number"),
            )
            .where(CanonicalAssessmentDb.initiative_id.is_not(None))
            .subquery()
        )
        assessments = list(
            database.scalars(
                select(CanonicalAssessmentDb)
                .join(ranked_assessments, ranked_assessments.c.assessment_id == CanonicalAssessmentDb.run_id)
                .where(ranked_assessments.c.row_number == 1)
            )
        )
        latest_by_initiative = {assessment.initiative_id: assessment for assessment in assessments if assessment.initiative_id is not None}
        pending_counts = dict(
            database.execute(
                select(LifecycleTransitionDb.initiative_id, func.count(LifecycleTransitionDb.id))
                .where(LifecycleTransitionDb.status == "PENDING")
                .group_by(LifecycleTransitionDb.initiative_id)
            ).all()
        )
        records: list[dict[str, object]] = []
        for initiative in initiatives:
            assessment = latest_by_initiative.get(initiative.id)
            dimensions = assessment.dimensions if assessment is not None else []
            records.append(
                {
                    "id": str(initiative.id),
                    "title": initiative.title,
                    "stage": initiative.current_stage,
                    "stage_name": {
                        "DI1": "Concept",
                        "DI2": "Pilot",
                        "DI3": "Test",
                        "DI4": "Implement",
                        "DI5": "Scale",
                    }.get(initiative.current_stage, initiative.current_stage),
                    "lifecycle_state": initiative.lifecycle_state,
                    "is_on_hold": initiative.is_on_hold,
                    "pending_review_count": pending_counts.get(initiative.id, 0),
                    "latest_score": assessment.composite_score if assessment is not None else None,
                    "latest_gate_outcome": assessment.gate_outcome if assessment is not None else None,
                    "latest_assessment_at": assessment.created_at.isoformat() if assessment is not None else None,
                    "dimensions": [
                        {
                            "dimension": dimension["dimension"],
                            "score": dimension["value"],
                            "summary": dimension["summary"],
                            "gaps": dimension["gaps"],
                        }
                        for dimension in dimensions
                    ],
                }
            )
        return {"initiative_count": len(records), "initiatives": records}
