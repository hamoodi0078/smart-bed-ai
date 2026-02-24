from datetime import datetime
import re

from ai.goal_strategy_engine import GoalStrategyEngine
from ai.personality_runtime import PersonalityRuntimeOrchestrator


def _parse_new_command(text: str) -> str:
    lower = (text or "").lower().strip()
    if lower in ("show session continuity", "session continuity"):
        return "show_session_continuity"
    if lower in ("voice pacing status", "show voice pacing"):
        return "voice_pacing_status"
    if lower in ("start recovery protocol",):
        return "start_recovery_protocol"
    if lower.startswith("set quiet window ") and re.match(r"^\d{2}:\d{2}-\d{2}:\d{2}$", text.split("set quiet window", 1)[1].strip()):
        return "set_quiet_window"
    if lower in ("show quiet window", "quiet window status"):
        return "show_quiet_window"
    return ""


def run_sanity_checks():
    runtime = PersonalityRuntimeOrchestrator()
    strategy = GoalStrategyEngine()

    profile = {
        "preferences": {"quiet_window": "23:00-07:00"},
        "goals": [{"id": "a1b2c3", "title": "sleep by 11 pm", "scope": "tonight", "status": "active"}],
    }
    runtime.ensure_shape(profile)
    strategy.ensure_shape(profile)

    # Continuity callback generation
    runtime.record_continuity_hint(profile, "therapist", "I am struggling with sleep anxiety lately")
    callback = runtime.continuity_callback_line(profile, "therapist")
    assert "Quick callback" in callback

    # Quiet-window suppression logic
    in_quiet = runtime._is_in_quiet_window("23:00-07:00", datetime(2026, 1, 1, 0, 30))
    out_quiet = runtime._is_in_quiet_window("23:00-07:00", datetime(2026, 1, 1, 12, 0))
    assert in_quiet is True
    assert out_quiet is False

    # Recovery protocol trigger conditions
    ok1, _, _ = strategy.mark_goal_missed(profile, "a1b2c3", cause_text="too tired")
    ok2, _, _ = strategy.mark_goal_missed(profile, "a1b2c3", cause_text="no time")
    assert ok1 and ok2
    assert strategy.should_trigger_recovery_protocol(profile, days=7, threshold=2) is True
    strategy.mark_recovery_prompted_today(profile)
    assert strategy.should_trigger_recovery_protocol(profile, days=7, threshold=2) is False

    # Command parsing checks for new commands
    assert _parse_new_command("show session continuity") == "show_session_continuity"
    assert _parse_new_command("voice pacing status") == "voice_pacing_status"
    assert _parse_new_command("start recovery protocol") == "start_recovery_protocol"
    assert _parse_new_command("set quiet window 23:00-07:00") == "set_quiet_window"
    assert _parse_new_command("show quiet window") == "show_quiet_window"

    print("Sanity checks passed.")


if __name__ == "__main__":
    run_sanity_checks()
