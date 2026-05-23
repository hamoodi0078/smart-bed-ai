"""Automated weekly health report generator for Smart Bed AI.

Compiles sleep stats, stress levels, hydration, prayer consistency,
automation effectiveness, and wellness insights into a comprehensive report.
Auto-sends every Sunday via push notification, WhatsApp, or email.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("health.weekly_health_report")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WeeklyHealthReport:
    """Generates comprehensive weekly health and wellness reports."""

    def __init__(self, *, report_day: int = 6, report_hour: int = 9):
        self._report_day = max(0, min(6, int(report_day)))  # 6 = Sunday
        self._report_hour = max(0, min(23, int(report_hour)))

    def ensure_shape(self, profile: dict) -> None:
        profile.setdefault("weekly_report", {})
        wr = profile["weekly_report"]
        wr.setdefault("last_report_date", "")
        wr.setdefault("reports_generated", 0)
        wr.setdefault("enabled", True)

    def should_generate(self, profile: dict, now: datetime | None = None) -> bool:
        """Check if it's time to generate the weekly report."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        wr = profile.get("weekly_report", {})
        if not wr.get("enabled", True):
            return False
        if now.weekday() != self._report_day:
            return False
        if now.hour != self._report_hour:
            return False
        today = now.date().isoformat()
        return wr.get("last_report_date", "") != today

    def generate(self, profile: dict, now: datetime | None = None) -> dict[str, Any]:
        """Generate the full weekly health report."""
        now = now or _utcnow()
        self.ensure_shape(profile)
        week_start = (now - timedelta(days=6)).date()
        week_end = now.date()

        report = {
            "generated_at": now.isoformat(),
            "period": f"{week_start.isoformat()} to {week_end.isoformat()}",
            "sleep": self._compile_sleep(profile),
            "wellness": self._compile_wellness(profile),
            "hydration": self._compile_hydration(profile),
            "prayer": self._compile_prayer(profile),
            "automations": self._compile_automations(profile),
            "recommendations": [],
        }

        report["recommendations"] = self._build_recommendations(report)
        report["summary_text"] = self._build_summary_text(report)
        report["whatsapp_text"] = self._build_whatsapp_text(report)

        profile["weekly_report"]["last_report_date"] = now.date().isoformat()
        profile["weekly_report"]["reports_generated"] = (
            int(profile["weekly_report"].get("reports_generated", 0)) + 1
        )

        return report

    # ------------------------------------------------------------------
    # Section compilers
    # ------------------------------------------------------------------

    def _compile_sleep(self, profile: dict) -> dict[str, Any]:
        sleep = profile.get("sleep", {})
        bed_hist = sleep.get("bedtime_history", [])[-7:]
        wake_hist = sleep.get("wake_history", [])[-7:]

        durations: list[float] = []
        for i in range(min(len(bed_hist), len(wake_hist))):
            try:
                bed = datetime.fromisoformat(str(bed_hist[-(i + 1)]))
                wake = datetime.fromisoformat(str(wake_hist[-(i + 1)]))
                if wake > bed:
                    h = (wake - bed).total_seconds() / 3600.0
                    if 2.0 <= h <= 16.0:
                        durations.append(h)
            except Exception:
                continue

        target = float(profile.get("preferences", {}).get("sleep_target_hours", 8.0) or 8.0)
        avg = sum(durations) / len(durations) if durations else 0
        debt = sum(max(0, target - d) for d in durations)

        bed_minutes = []
        for raw in bed_hist:
            try:
                dt = datetime.fromisoformat(str(raw))
                bed_minutes.append(dt.hour * 60 + dt.minute)
            except Exception:
                pass

        consistency = 100
        if len(bed_minutes) > 1:
            import statistics
            try:
                std = statistics.stdev(bed_minutes)
                consistency = max(0, min(100, int(100 - std)))
            except Exception:
                pass

        return {
            "nights_tracked": len(durations),
            "avg_hours": round(avg, 1),
            "target_hours": target,
            "total_debt_hours": round(debt, 1),
            "consistency_score": consistency,
            "short_nights": sum(1 for d in durations if d < 6),
            "best_night_hours": round(max(durations), 1) if durations else 0,
            "worst_night_hours": round(min(durations), 1) if durations else 0,
        }

    def _compile_wellness(self, profile: dict) -> dict[str, Any]:
        stress_history = profile.get("stress", {}).get("history", [])
        recent = stress_history[-7:]
        scores = [int(h.get("score", 0)) for h in recent]

        overthinking = profile.get("daily_life", {}).get("overthinking_entries", [])
        recent_overthinking = len([
            e for e in overthinking
            if str(e.get("at", "")) >= (_utcnow() - timedelta(days=7)).isoformat()
        ])

        return {
            "avg_stress_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "high_stress_days": sum(1 for s in scores if s >= 60),
            "overthinking_entries": recent_overthinking,
            "stress_trend": "improving" if len(scores) >= 3 and scores[-1] < scores[0]
                           else ("worsening" if len(scores) >= 3 and scores[-1] > scores[0] else "stable"),
        }

    def _compile_hydration(self, profile: dict) -> dict[str, Any]:
        history = profile.get("hydration", {}).get("history", [])
        cutoff = (_utcnow() - timedelta(days=7)).date().isoformat()
        recent = [d for d in history if str(d.get("date", "")) >= cutoff]

        if not recent:
            return {"days_tracked": 0, "avg_ml": 0, "goals_met": 0}

        intakes = [int(d.get("intake_ml", 0)) for d in recent]
        goals_met = sum(1 for d in recent if d.get("goal_reached", False))

        return {
            "days_tracked": len(recent),
            "avg_ml": round(sum(intakes) / len(intakes)) if intakes else 0,
            "goals_met": goals_met,
            "goal_rate_pct": round(goals_met / len(recent) * 100, 1) if recent else 0,
        }

    def _compile_prayer(self, profile: dict) -> dict[str, Any]:
        islamic = profile.get("islamic", {})
        stats = islamic.get("prayer_stats", {})
        tahajjud_history = islamic.get("tahajjud_history", [])
        cutoff = (_utcnow() - timedelta(days=7)).date().isoformat()
        recent_tahajjud = [h for h in tahajjud_history if str(h.get("date", "")) >= cutoff]

        return {
            "total_reminders": int(stats.get("total_reminders_sent", 0)),
            "acknowledged": int(stats.get("acknowledged_count", 0)),
            "tahajjud_prayed": sum(1 for h in recent_tahajjud if h.get("prayed", False)),
            "tahajjud_attempted": len(recent_tahajjud),
        }

    def _compile_automations(self, profile: dict) -> dict[str, Any]:
        proactive = profile.get("proactive", {})
        history = proactive.get("history", [])
        cutoff = (_utcnow() - timedelta(days=7)).isoformat()
        recent = [h for h in history if str(h.get("executed_at", "")) >= cutoff]

        return {
            "total_triggered": len(recent),
            "types": list(set(str(h.get("key", "")) for h in recent)),
        }

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(self, report: dict) -> list[str]:
        recs: list[str] = []
        sleep = report.get("sleep", {})
        wellness = report.get("wellness", {})
        hydration = report.get("hydration", {})

        if sleep.get("avg_hours", 0) < 7:
            recs.append("Your average sleep is below 7 hours. Try going to bed 30 minutes earlier.")
        if sleep.get("consistency_score", 100) < 60:
            recs.append("Your bedtime varies a lot. A consistent schedule improves sleep quality.")
        if sleep.get("total_debt_hours", 0) > 3:
            recs.append(f"You have {sleep['total_debt_hours']:.0f}h sleep debt. Plan a recovery weekend.")
        if sleep.get("short_nights", 0) >= 3:
            recs.append("Too many short nights this week. Prioritize sleep duration.")

        if wellness.get("avg_stress_score", 0) > 60:
            recs.append("High stress this week. Incorporate daily breathing exercises.")
        if wellness.get("overthinking_entries", 0) >= 5:
            recs.append("Frequent overthinking. Try journaling before bed to clear your mind.")

        if hydration.get("goal_rate_pct", 0) < 50:
            recs.append("Hydration goal met less than half the time. Set more reminders.")

        if not recs:
            recs.append("Excellent week! MashaAllah, keep up the great habits.")

        return recs[:5]

    # ------------------------------------------------------------------
    # Text formatters
    # ------------------------------------------------------------------

    def _build_summary_text(self, report: dict) -> str:
        sleep = report.get("sleep", {})
        wellness = report.get("wellness", {})
        hydration = report.get("hydration", {})
        recs = report.get("recommendations", [])

        lines = [
            f"Weekly Health Report — {report.get('period', '')}",
            "",
            "SLEEP",
            f"  Avg: {sleep.get('avg_hours', 0):.1f}h/night ({sleep.get('nights_tracked', 0)} nights)",
            f"  Consistency: {sleep.get('consistency_score', 0)}/100",
            f"  Sleep debt: {sleep.get('total_debt_hours', 0):.1f}h",
            "",
            "WELLNESS",
            f"  Avg stress: {wellness.get('avg_stress_score', 0):.0f}/100",
            f"  High stress days: {wellness.get('high_stress_days', 0)}",
            "",
            "HYDRATION",
            f"  Goals met: {hydration.get('goals_met', 0)}/{hydration.get('days_tracked', 0)} days",
            "",
            "RECOMMENDATIONS",
        ]
        for r in recs:
            lines.append(f"  - {r}")

        return "\n".join(lines)

    def to_pdf(self, report: dict[str, Any], output_path: str) -> str:
        """Render *report* (from ``generate()``) to a PDF file at *output_path*.

        Returns the absolute path of the written file.
        Raises RuntimeError if reportlab is not installed.
        """
        from reports.pdf_generator import generate_weekly_pdf
        return generate_weekly_pdf(report, output_path)

    def to_html_pdf(self, report: dict[str, Any], output_path: str) -> str:
        """Render *report* to PDF via WeasyPrint (HTML/CSS renderer).

        Returns the absolute path of the written file.
        Raises RuntimeError if weasyprint is not installed.
        """
        from reports.html_report_renderer import render_pdf
        return render_pdf(report, output_path)

    def to_html(self, report: dict[str, Any]) -> str:
        """Return the report as a styled HTML document string."""
        from reports.html_report_renderer import render_html
        return render_html(report)

    def _build_whatsapp_text(self, report: dict) -> str:
        sleep = report.get("sleep", {})
        recs = report.get("recommendations", [])

        lines = [
            f"Weekly Report {report.get('period', '')}",
            f"Sleep: {sleep.get('avg_hours', 0):.1f}h avg, {sleep.get('consistency_score', 0)}/100 consistency",
            f"Debt: {sleep.get('total_debt_hours', 0):.1f}h",
        ]
        if recs:
            lines.append(f"Tip: {recs[0]}")

        return "\n".join(lines)
