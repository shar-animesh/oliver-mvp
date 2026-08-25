"""Static and functional checks for the versioned transition benchmark corpus."""

import json
from pathlib import Path

from scripts.run_transition_benchmarks import _case_failures

_CORPUS_PATH = Path(__file__).parent / "evaluation" / "transition-benchmarks.json"


def _corpus() -> dict[str, object]:
    return json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))


def test_benchmark_cases_have_unique_ids_and_valid_equivalence_references() -> None:
    cases = _corpus()["cases"]
    assert isinstance(cases, list)
    case_ids = [case["id"] for case in cases]

    assert len(case_ids) == len(set(case_ids))
    for case in cases:
        equivalent_to = case.get("equivalent_to")
        assert equivalent_to is None or equivalent_to in case_ids


def test_stronger_alternative_case_preserves_dimension_boundaries() -> None:
    cases = {case["id"]: case for case in _corpus()["cases"]}
    case = cases["di1-stronger-non-ai-alternative"]

    assert case["expected_dimension_states"] == {
        "ideaQuality": "CONCERN",
        "technicalFeasibility": "SATISFIED",
        "executionReadiness": "UNKNOWN",
    }


def test_case_failures_detect_semantic_and_participant_output_regressions() -> None:
    case = {
        "expected_gate_outcome": "HOLD_FOR_EVIDENCE",
        "expected_response_depth": "BRIEF",
        "expected_composite_score_present": False,
        "expected_dimension_states": {"technicalFeasibility": "SATISFIED"},
        "expected_criterion_states": {"DI1_DI2_PILOT_SCOPE": "UNKNOWN"},
        "forbidden_email_patterns": [r"\bairworthiness\b", r"\b\d+[ -]weeks?\b"],
    }
    valid_result = {
        "gate_outcome": "HOLD_FOR_EVIDENCE",
        "response_depth": "BRIEF",
        "composite_score": None,
        "dimensions": [{"dimension": "technicalFeasibility", "state": "SATISFIED"}],
        "criteria": [{"criterion_id": "DI1_DI2_PILOT_SCOPE", "state": "UNKNOWN"}],
        "email_html": "<p>Please clarify the controlled pilot scope.</p>",
    }
    assert _case_failures(case, valid_result) == []

    invalid_result = {
        **valid_result,
        "dimensions": [{"dimension": "technicalFeasibility", "state": "CONCERN"}],
        "email_html": "<p>Complete this in 4 weeks before an airworthiness decision.</p>",
    }
    failures = _case_failures(case, invalid_result)
    assert "dimension:technicalFeasibility:CONCERN" in failures
    assert r"forbidden_email_pattern:\bairworthiness\b" in failures
    assert r"forbidden_email_pattern:\b\d+[ -]weeks?\b" in failures
