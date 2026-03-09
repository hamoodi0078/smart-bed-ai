from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict

from database.repositories import EventRepository, SleepSessionRepository
from time_utils import utcnow

SummaryPayload = Dict[str, Any]


def _as_event_count(events: list[Any], event_type: str) -> int:
    key = str(event_type or "").strip().lower()
    return sum(1 for row in events if str(getattr(row, "event_type", "") or "").strip().lower() == key)


def _format_optional_minutes(minutes: int | None) -> str:
    return "N/A" if minutes is None else f"{int(minutes)} min"


def _format_optional_float(value: float | None, digits: int = 1) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def build_daily_summary(
    user_id: str,
    *,
    event_repo: EventRepository,
    sleep_repo: SleepSessionRepository,
) -> SummaryPayload:
    target_date = utcnow().date() - timedelta(days=1)
    events = event_repo.get_events_for_date(user_id, target_date)
    sleep_session = sleep_repo.get_session_by_date(user_id, target_date)

    scenes_used_count = _as_event_count(events, "sceneactivated")
    winddowns_completed = _as_event_count(events, "winddownstarted")
    automations_fired = _as_event_count(events, "automationfired")

    summary_title = "Your Manues daily sleep summary"
    if winddowns_completed >= 1 and scenes_used_count >= 1:
        readiness_comment = "You followed your wind-down plan. Great job."
    elif scenes_used_count >= 1:
        readiness_comment = "You used scenes, but skipped wind-down."
    else:
        readiness_comment = "No sleep activity recorded last night."

    plain_lines = [
        summary_title,
        f"Date (UTC): {target_date.isoformat()}",
        readiness_comment,
        f"Scenes used: {scenes_used_count}",
        f"Wind-downs started: {winddowns_completed}",
        f"Automations fired: {automations_fired}",
    ]
    whatsapp_lines = [
        summary_title,
        f"{target_date.isoformat()} (UTC)",
        f"1) Scenes: {scenes_used_count} | Wind-downs: {winddowns_completed}",
        f"2) Automations: {automations_fired}",
    ]

    if sleep_session is not None:
        total_sleep_minutes = sleep_session.total_sleep_minutes
        restlessness_score = sleep_session.restlessness_score
        plain_lines.append(f"Total sleep: {_format_optional_minutes(total_sleep_minutes)}")
        plain_lines.append(f"Restlessness score: {_format_optional_float(restlessness_score, digits=1)}")
        whatsapp_lines.append(
            f"3) Sleep: {_format_optional_minutes(total_sleep_minutes)} | Restlessness: {_format_optional_float(restlessness_score, digits=1)}"
        )
    else:
        whatsapp_lines.append(f"3) {readiness_comment}")

    return {
        "subject": summary_title,
        "plain_text": "\n".join(plain_lines),
        "whatsapp_text": "\n".join(whatsapp_lines),
        "metadata": {
            "date": target_date.isoformat(),
            "scenes_used_count": scenes_used_count,
            "winddowns_completed": winddowns_completed,
            "automations_fired": automations_fired,
            "has_sleep_session": sleep_session is not None,
        },
    }


def build_monthly_summary(
    user_id: str,
    year: int,
    month: int,
    *,
    event_repo: EventRepository,
    sleep_repo: SleepSessionRepository,
) -> SummaryPayload:
    del event_repo  # Included for shared call signatures between channels.
    sessions = sleep_repo.get_sessions_for_month(user_id, year, month, limit=40)

    nights_tracked = len(sessions)
    sleep_minutes_values = [int(row.total_sleep_minutes) for row in sessions if row.total_sleep_minutes is not None]
    restlessness_values = [float(row.restlessness_score) for row in sessions if row.restlessness_score is not None]

    average_sleep_minutes = int(round(sum(sleep_minutes_values) / len(sleep_minutes_values))) if sleep_minutes_values else None
    average_restlessness = round(sum(restlessness_values) / len(restlessness_values), 2) if restlessness_values else None
    winddowns_completed_total = sum(int(row.winddowns_completed or 0) for row in sessions)

    summary_title = f"Your Manues monthly sleep report – {year}-{month:02d}"
    if nights_tracked >= 20 and average_restlessness is not None and average_restlessness < 40:
        main_highlight = "Your sleep consistency this month was strong."
    elif nights_tracked >= 10:
        main_highlight = "You are building a sleep habit. Keep going."
    else:
        main_highlight = "Not enough data this month. Try using Manues more nights."

    avg_sleep_text = "N/A" if average_sleep_minutes is None else f"{average_sleep_minutes} min"
    avg_restlessness_text = "N/A" if average_restlessness is None else f"{average_restlessness:.2f}"

    plain_lines = [
        summary_title,
        f"Period: {year}-{month:02d} (UTC)",
        "",
        "Monthly highlight:",
        main_highlight,
        "",
        f"Nights tracked: {nights_tracked}",
        f"Average sleep minutes: {avg_sleep_text}",
        f"Average restlessness: {avg_restlessness_text}",
        f"Total wind-downs completed: {winddowns_completed_total}",
        "Insights are based on up to 40 recent sleep sessions in this month.",
        "Keep tracking your nights to improve trend quality.",
    ]
    whatsapp_lines = [
        f"{year}-{month:02d} monthly sleep report",
        f"- Nights tracked: {nights_tracked}",
        f"- Avg sleep: {avg_sleep_text}",
        f"- Avg restlessness: {avg_restlessness_text}",
        f"- {main_highlight}",
    ]

    return {
        "subject": summary_title,
        "plain_text": "\n".join(plain_lines),
        "whatsapp_text": "\n".join(whatsapp_lines),
        "metadata": {
            "year": int(year),
            "month": int(month),
            "nights_tracked": nights_tracked,
            "average_sleep_minutes": average_sleep_minutes,
            "average_restlessness": average_restlessness,
            "winddowns_completed_total": winddowns_completed_total,
        },
    }
