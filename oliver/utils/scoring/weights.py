"""Versioned scoring weights: policy data, not hard-coded scoring logic."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, field_validator

from .models import DIStage

STAGES = tuple(stage.value for stage in DIStage)
DIMENSIONS = (
    "ideaCompleteness",
    "ideaQuality",
    "strategicValue",
    "technicalFeasibility",
    "executionReadiness",
)
DEFAULT_VERSION = "weight-set/3.1.0"


class WeightSet(BaseModel):
    """A validated, versioned stage-adaptive weight set."""

    version: str
    model_version: str
    weights: dict[str, dict[str, int]]

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, value: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
        for stage in STAGES:
            if stage not in value:
                raise ValueError(f"Weight set is missing {stage}")
            missing = set(DIMENSIONS) - value[stage].keys()
            if missing:
                raise ValueError(f"{stage} is missing dimensions: {sorted(missing)}")
            if sum(value[stage][dimension] for dimension in DIMENSIONS) != 100:
                raise ValueError(f"{stage} weights must total 100")
        return value

    def weights_for(self, stage: str) -> dict[str, int]:
        """Return weights for a validated DI stage."""
        return self.weights[stage]


def _load_weight_sets() -> dict[str, WeightSet]:
    directories = [Path(__file__).resolve().parent / "data"]
    if external_directory := os.getenv("OLIVER_WEIGHTS_DIR"):
        directories.append(Path(external_directory))
    registry: dict[str, WeightSet] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            weight_set = WeightSet.model_validate_json(path.read_text(encoding="utf-8"))
            registry[weight_set.version] = weight_set
    return registry


@lru_cache
def active_weight_set() -> WeightSet:
    """Load the configured set, defaulting to the bundled historic policy."""
    registry = _load_weight_sets()
    version = os.getenv("OLIVER_WEIGHT_SET", DEFAULT_VERSION)
    if version not in registry:
        raise ValueError(f"Unknown OLIVER_WEIGHT_SET {version!r}; available: {sorted(registry)}")
    return registry[version]
