from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.types import Effect


AutomationTrigger = Callable[[dict[str, Any]], bool]
AutomationAction = Callable[[dict[str, Any]], list[Effect]]
WindowKeyResolver = Callable[[dict[str, Any]], str | None]


@dataclass(frozen=True)
class Automation:
    """Declarative automation with pure trigger/action callables."""

    name: str
    trigger: AutomationTrigger
    action: AutomationAction
    cooldown_minutes: int = 60
    enabled: bool = True
    window_key: WindowKeyResolver | None = None
