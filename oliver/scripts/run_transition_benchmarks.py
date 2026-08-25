"""Run the non-persistent transition corpus against a local Oliver API."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from html import unescape
from pathlib import Path

import httpx

from config import get_settings

_INTERNAL_POLICY_ID = re.compile(r"\bDI[1-5]_DI[1-5]_[A-Z0-9_]+\b")


def _visible_email_text(email_html: str) -> str:
    """Return compact visible text for benchmark-only content assertions."""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", email_html)).split())


def _result_states(result: dict[str, object], field: str, identity: str) -> dict[str, str]:
    items = result.get(field, [])
    if not isinstance(items, list):
        return {}
    return {str(item[identity]): str(item["state"]) for item in items if isinstance(item, dict) and identity in item and "state" in item}


def _case_failures(case: dict[str, object], result: dict[str, object]) -> list[str]:
    """Evaluate stable functional expectations without requiring exact model prose."""
    failures: list[str] = []
    actual_gate = result.get("gate_outcome")
    if actual_gate != case["expected_gate_outcome"]:
        failures.append(f"gate_outcome:{actual_gate}")

    expected_depth = case.get("expected_response_depth")
    if expected_depth is not None and result.get("response_depth") != expected_depth:
        failures.append(f"response_depth:{result.get('response_depth')}")

    expected_score_present = case.get("expected_composite_score_present")
    if expected_score_present is not None:
        actual_score_present = result.get("composite_score") is not None
        if actual_score_present is not expected_score_present:
            failures.append(f"composite_score_present:{actual_score_present}")

    dimension_states = _result_states(result, "dimensions", "dimension")
    for dimension, expected_state in dict(case.get("expected_dimension_states", {})).items():
        if dimension_states.get(dimension) != expected_state:
            failures.append(f"dimension:{dimension}:{dimension_states.get(dimension)}")

    criterion_states = _result_states(result, "criteria", "criterion_id")
    for criterion_id, expected_state in dict(case.get("expected_criterion_states", {})).items():
        if criterion_states.get(criterion_id) != expected_state:
            failures.append(f"criterion:{criterion_id}:{criterion_states.get(criterion_id)}")

    email_html = str(result.get("email_html") or "")
    if _INTERNAL_POLICY_ID.search(email_html):
        failures.append("internal_policy_id_exposed")
    if "Policy basis:" in email_html:
        failures.append("internal_policy_basis_exposed")
    visible_email = _visible_email_text(email_html)
    for pattern in case.get("forbidden_email_patterns", []):
        if re.search(str(pattern), visible_email, re.IGNORECASE):
            failures.append(f"forbidden_email_pattern:{pattern}")
    return failures


def main() -> int:
    settings = get_settings()
    corpus_path = Path(__file__).resolve().parents[1] / "tests" / "evaluation" / "transition-benchmarks.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    gateway_key = settings.ADMIN_GATEWAY_API_KEY.get_secret_value() or settings.INTERNAL_API_KEY.get_secret_value()
    benchmark_identity = os.getenv("OLIVER_BENCHMARK_IDENTITY")
    if benchmark_identity is None:
        benchmark_identity = next(iter(sorted(settings.admin_identities)), None)
    if benchmark_identity is None:
        raise ValueError("Configure OLIVER_BENCHMARK_IDENTITY or at least one local ADMIN_IDENTITIES value")
    headers = {
        "X-Internal-Api-Key": gateway_key,
        "X-Oliver-Admin-Identity": benchmark_identity,
    }
    results: list[dict[str, object]] = []
    selected_ids = set(sys.argv[1:])
    end_to_end_timeout = settings.OPENAI_REQUEST_TIMEOUT_SECONDS * (settings.ASSESSMENT_RESPONSE_RETRIES + 2) + 30
    with httpx.Client(base_url="http://127.0.0.1:8001", headers=headers, timeout=end_to_end_timeout) as client:
        priority = {
            "di1-low-context": 0,
            "di1-management-pressure": 1,
            "di1-medium-context": 2,
            "di1-full-context": 3,
        }
        cases = [case for case in corpus["cases"] if not selected_ids or case["id"] in selected_ids]
        if selected_ids - {case["id"] for case in cases}:
            unknown = sorted(selected_ids - {case["id"] for case in cases})
            raise ValueError(f"Unknown benchmark case IDs: {unknown}")
        for case in sorted(cases, key=lambda item: priority.get(item["id"], len(priority))):
            started = time.monotonic()
            try:
                response = client.post(
                    "/api/v1/assessment/test",
                    json={
                        "subject": case["subject"],
                        "evidence": case["evidence"],
                        "current_stage": case["current_stage"],
                    },
                )
            except httpx.HTTPError as error:
                summary = {
                    "id": case["id"],
                    "expected": case["expected_gate_outcome"],
                    "actual": None,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "error": type(error).__name__,
                    "passed": False,
                }
                results.append(summary)
                print(json.dumps(summary), flush=True)
                continue
            elapsed = round(time.monotonic() - started, 2)
            if response.is_error:
                try:
                    detail = response.json().get("detail", "Assessment request failed")
                except (ValueError, AttributeError):
                    detail = "Assessment request failed"
                summary = {
                    "id": case["id"],
                    "expected": case["expected_gate_outcome"],
                    "actual": None,
                    "elapsed_seconds": elapsed,
                    "status_code": response.status_code,
                    "error": detail,
                    "passed": False,
                }
                results.append(summary)
                print(json.dumps(summary), flush=True)
                continue
            result = response.json()
            email_html = result.get("email_html") or ""
            actual = result["gate_outcome"]
            failures = _case_failures(case, result)
            summary = {
                "id": case["id"],
                "expected": case["expected_gate_outcome"],
                "actual": actual,
                "response_depth": result["response_depth"],
                "composite_score": result["composite_score"],
                "email_generated": bool(email_html),
                "internal_id_exposed": bool(_INTERNAL_POLICY_ID.search(email_html)),
                "dimension_states": _result_states(result, "dimensions", "dimension"),
                "criterion_states": _result_states(result, "criteria", "criterion_id"),
                "elapsed_seconds": elapsed,
                "failures": failures,
                "passed": not failures,
            }
            results.append(summary)
            print(json.dumps(summary), flush=True)

    results_by_id = {item["id"]: item for item in results}
    equivalence_checks: list[dict[str, object]] = []
    cases_by_id = {case["id"]: case for case in cases}
    for case_id, case in cases_by_id.items():
        equivalent_to = case.get("equivalent_to")
        if equivalent_to is None or case_id not in results_by_id or equivalent_to not in results_by_id:
            continue
        actual = results_by_id[case_id]
        reference = results_by_id[equivalent_to]
        fields = ("actual", "composite_score", "dimension_states", "criterion_states")
        passed = all(actual.get(field) == reference.get(field) for field in fields)
        equivalence_checks.append({"case": case_id, "equivalent_to": equivalent_to, "passed": passed})
    pressure_check = next((check for check in equivalence_checks if check["case"] == "di1-management-pressure"), None)
    pressure_invariant = bool(pressure_check["passed"]) if pressure_check is not None else None
    final = {
        "corpus_version": corpus["version"],
        "passed": all(bool(item["passed"]) for item in results) and all(bool(check["passed"]) for check in equivalence_checks),
        "pressure_invariant": pressure_invariant,
        "equivalence_checks": equivalence_checks,
        "cases": results,
    }
    print(json.dumps(final, indent=2), flush=True)
    return 0 if final["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
