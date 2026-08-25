"""Canonical Design and Innovation stage identifiers and approved names."""

from enum import Enum


class DIStage(str, Enum):
    """Authoritative Design and Innovation lifecycle stage."""

    DI1 = "DI1"
    DI2 = "DI2"
    DI3 = "DI3"
    DI4 = "DI4"
    DI5 = "DI5"

    @property
    def display_name(self) -> str:
        """Return the approved business name for this lifecycle stage."""
        return {
            DIStage.DI1: "Concept",
            DIStage.DI2: "Pilot",
            DIStage.DI3: "Test",
            DIStage.DI4: "Implement",
            DIStage.DI5: "Scale",
        }[self]

    @property
    def next_stage(self) -> "DIStage | None":
        """Return the following stage, or none when Scale is reached."""
        stages = list(DIStage)
        index = stages.index(self)
        return stages[index + 1] if index + 1 < len(stages) else None

    @property
    def previous_stage(self) -> "DIStage":
        """Return the preceding stage without moving earlier than Concept."""
        stages = list(DIStage)
        return stages[max(0, stages.index(self) - 1)]
