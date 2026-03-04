from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Effect:
    """Represents a side-effect request emitted by command logic."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResult:
    """Pure command result that can be applied by runtime effect handlers."""

    text: str
    effects: tuple[Effect, ...] = field(default_factory=tuple)
    followup_state: dict[str, Any] = field(default_factory=dict)
