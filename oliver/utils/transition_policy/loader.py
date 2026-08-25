"""Load validated transition policy from versioned data files."""

import os
from functools import lru_cache
from pathlib import Path

from utils.stages import DIStage

from .models import StageTransitionPolicy, TerminalStagePolicy, TransitionPolicySet

DEFAULT_VERSION = "transition-policy/1.1.0"


def _load_policy_sets() -> dict[str, TransitionPolicySet]:
    directories = [Path(__file__).resolve().parent / "data"]
    if external_directory := os.getenv("OLIVER_TRANSITION_POLICY_DIR"):
        directories.append(Path(external_directory))
    registry: dict[str, TransitionPolicySet] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            policy_set = TransitionPolicySet.model_validate_json(path.read_text(encoding="utf-8"))
            if policy_set.version in registry:
                raise ValueError(f"Duplicate transition policy version {policy_set.version!r} loaded from {path}")
            registry[policy_set.version] = policy_set
    return registry


@lru_cache
def active_transition_policy_set() -> TransitionPolicySet:
    """Return the configured transition policy or fail on invalid configuration."""
    registry = _load_policy_sets()
    version = os.getenv("OLIVER_TRANSITION_POLICY", DEFAULT_VERSION)
    if version not in registry:
        raise ValueError(f"Unknown OLIVER_TRANSITION_POLICY {version!r}; available: {sorted(registry)}")
    visited: set[str] = set()

    def resolve(selected: str) -> TransitionPolicySet:
        if selected in visited:
            raise ValueError(f"Circular transition policy inheritance involving {selected!r}")
        if selected not in registry:
            raise ValueError(f"Transition policy {selected!r} extends an unknown policy")
        visited.add(selected)
        document = registry[selected]
        if document.extends is None:
            transitions = dict(document.transitions)
            terminal_stages = dict(document.terminal_stages)
        else:
            base = resolve(document.extends)
            transitions = {**base.transitions, **document.transitions}
            terminal_stages = {**base.terminal_stages, **document.terminal_stages}
        visited.remove(selected)
        return TransitionPolicySet(
            version=document.version,
            transitions=transitions,
            terminal_stages=terminal_stages,
        )

    return resolve(version)


def policy_for_stage(stage: DIStage) -> StageTransitionPolicy | None:
    """Return an approved policy for the current stage, if one exists."""
    return active_transition_policy_set().transitions.get(stage.value)


def terminal_policy_for_stage(stage: DIStage) -> TerminalStagePolicy | None:
    """Return an approved monitoring policy for a terminal lifecycle stage."""
    return active_transition_policy_set().terminal_stages.get(stage.value)
