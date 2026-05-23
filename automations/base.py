from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.types import Effect


AutomationTrigger = Callable[[dict[str, Any]], bool]
AutomationAction = Callable[[dict[str, Any]], list[Effect]]
WindowKeyResolver = Callable[[dict[str, Any]], str | None]
AUTOMATION_COOLDOWN_MINUTES_MIN = 60
AUTOMATION_COOLDOWN_MINUTES_MAX = 1440
AUTOMATION_CRITICALITY_CRITICAL = "critical"
AUTOMATION_CRITICALITY_NON_CRITICAL = "non_critical"


def normalize_cooldown_minutes(value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = AUTOMATION_COOLDOWN_MINUTES_MIN
    if parsed < AUTOMATION_COOLDOWN_MINUTES_MIN:
        return AUTOMATION_COOLDOWN_MINUTES_MIN
    if parsed > AUTOMATION_COOLDOWN_MINUTES_MAX:
        return AUTOMATION_COOLDOWN_MINUTES_MAX
    return parsed


def normalize_automation_criticality(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == AUTOMATION_CRITICALITY_CRITICAL:
        return AUTOMATION_CRITICALITY_CRITICAL
    return AUTOMATION_CRITICALITY_NON_CRITICAL


@dataclass(frozen=True)
class Automation:
    """Declarative automation with pure trigger/action callables.

    Scheduling modes (mutually exclusive):
    - ``cron_expr`` set  → fires when ``core.cron_utils.should_fire_now`` returns True
                           (e.g. ``"0 22 * * *"`` fires at 22:00 every day).
    - ``cron_expr`` None → fires when ``cooldown_minutes`` has elapsed since last run.
    """

    name: str
    trigger: AutomationTrigger
    action: AutomationAction
    cooldown_minutes: int = 60
    criticality: str = AUTOMATION_CRITICALITY_NON_CRITICAL
    enabled: bool = True
    window_key: WindowKeyResolver | None = None
    cron_expr: str | None = None
