"""HTML + WeasyPrint weekly health report renderer for Smart Bed AI.

Converts a WeeklyHealthReport dict to a styled HTML page, then (optionally)
to a PDF via WeasyPrint.  All CSS is inlined so WeasyPrint can render without
an external stylesheet.

Public API
----------
render_html(report)                -> str          (full HTML document)
render_pdf(report, output_path)    -> str          (absolute path to .pdf)
generate_weekly_html_pdf(report, output_path) -> str  (module-level wrapper)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("reports.html_report_renderer")

try:
    import weasyprint as _wp
    _WEASYPRINT_AVAILABLE = True
except ImportError:
    _WEASYPRINT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Brand palette (matches pdf_generator.py)
# ---------------------------------------------------------------------------
_TEAL = "#1A7F8E"
_DARK = "#1C2B36"
_LIGHT = "#EAF6F8"
_ACCENT = "#F4A261"
_GREY = "#6B7280"
_GREEN = "#16A34A"
_RED = "#DC2626"

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
_CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    color: {_DARK};
    background: #fff;
    font-size: 13px;
    line-height: 1.5;
    padding: 28px 36px;
}}
h1 {{ font-size: 22px; color: {_DARK}; margin-bottom: 2px; }}
.subtitle {{ color: {_GREY}; font-size: 11px; margin-bottom: 16px; }}
hr.top {{ border: none; border-top: 2px solid {_TEAL}; margin-bottom: 20px; }}

/* Section header */
.section-header {{
    background: {_TEAL};
    color: #fff;
    font-size: 13px;
    font-weight: bold;
    padding: 5px 10px;
    margin-top: 18px;
    margin-bottom: 8px;
    border-radius: 3px;
}}

/* Metrics table */
table.metrics {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 6px;
}}
table.metrics tr:nth-child(odd) {{ background: {_LIGHT}; }}
table.metrics td {{
    padding: 5px 8px;
    vertical-align: middle;
}}
td.label {{ color: {_GREY}; width: 34%; }}
td.bar-cell {{ width: 40%; }}
td.value {{ font-weight: bold; text-align: right; width: 26%; }}

/* Progress bar */
.bar-outer {{
    background: #E5E7EB;
    border-radius: 4px;
    height: 9px;
    width: 100%;
    overflow: hidden;
}}
.bar-inner {{
    height: 9px;
    border-radius: 4px;
}}
.bar-good  {{ background: {_TEAL}; }}
.bar-warn  {{ background: {_ACCENT}; }}
.bar-bad   {{ background: {_RED}; }}

/* Trend badge */
.trend-stable  {{ color: {_GREY}; }}
.trend-improving {{ color: {_GREEN}; }}
.trend-worsening {{ color: {_RED}; }}

/* Recommendations */
ul.recs {{ padding-left: 18px; margin-top: 4px; }}
ul.recs li {{ margin-bottom: 5px; }}

/* Footer */
.footer {{
    margin-top: 28px;
    border-top: 1px solid {_GREY};
    padding-top: 8px;
    font-size: 9px;
    color: {_GREY};
    text-align: center;
}}

/* Automation types */
.types {{ color: {_GREY}; font-size: 11px; margin-top: 3px; }}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bar_html(value: float, max_value: float) -> str:
    ratio = min(1.0, max(0.0, value / max_value)) if max_value else 0.0
    pct = round(ratio * 100, 1)
    cls = "bar-good" if ratio >= 0.6 else ("bar-warn" if ratio >= 0.3 else "bar-bad")
    return (
        f'<div class="bar-outer">'
        f'<div class="bar-inner {cls}" style="width:{pct}%"></div>'
        f'</div>'
    )


def _metric_rows(rows: list[tuple[str, Any, str, float, float]]) -> str:
    """rows: (label, value, unit, num_value, max_value)"""
    html = '<table class="metrics">'
    for label, value, unit, num_val, max_val in rows:
        bar = _bar_html(num_val, max_val)
        html += (
            f"<tr>"
            f'<td class="label">{label}</td>'
            f'<td class="bar-cell">{bar}</td>'
            f'<td class="value">{value} <span style="font-weight:normal;color:{_GREY}">{unit}</span></td>'
            f"</tr>"
        )
    html += "</table>"
    return html


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _sleep_section(sleep: dict) -> str:
    avg = float(sleep.get("avg_hours", 0))
    target = float(sleep.get("target_hours", 8))
    consistency = float(sleep.get("consistency_score", 0))
    debt = float(sleep.get("total_debt_hours", 0))
    nights = int(sleep.get("nights_tracked", 0))
    short = int(sleep.get("short_nights", 0))

    rows = [
        ("Average sleep", f"{avg:.1f}h", f"/ {target:.0f}h target", avg, target or 8),
        ("Consistency score", f"{consistency:.0f}", "/ 100", consistency, 100),
        ("Sleep debt", f"{debt:.1f}h", "this week", debt, max(debt, 5)),
        ("Nights tracked", str(nights), "nights", nights, 7),
        ("Short nights (&lt;6h)", str(short), "nights", short, 7),
    ]
    return '<div class="section-header">Sleep</div>' + _metric_rows(rows)


def _wellness_section(wellness: dict) -> str:
    avg_stress = float(wellness.get("avg_stress_score", 0))
    high_stress = int(wellness.get("high_stress_days", 0))
    overthinking = int(wellness.get("overthinking_entries", 0))
    trend = str(wellness.get("stress_trend", "stable")).lower()
    trend_cls = f"trend-{trend}" if trend in ("improving", "worsening", "stable") else "trend-stable"

    rows = [
        ("Average stress level", f"{avg_stress:.0f}", "/ 100", avg_stress, 100),
        ("High-stress days", str(high_stress), "days", high_stress, 7),
        ("Overthinking entries", str(overthinking), "entries", overthinking, 10),
    ]
    html = '<div class="section-header">Wellness &amp; Stress</div>'
    html += _metric_rows(rows)
    html += f'<p style="margin-top:4px;font-size:11px;">Stress trend: <span class="{trend_cls}"><b>{trend.capitalize()}</b></span></p>'
    return html


def _hydration_section(hydration: dict) -> str:
    days = int(hydration.get("days_tracked", 0))
    avg_ml = int(hydration.get("avg_ml", 0))
    goals_met = int(hydration.get("goals_met", 0))
    goal_rate = float(hydration.get("goal_rate_pct", 0))

    rows = [
        ("Average daily intake", str(avg_ml), "ml / day", avg_ml, 3000),
        ("Goals met", str(goals_met), f"/ {days} days", goals_met, days or 7),
        ("Goal achievement", f"{goal_rate:.0f}%", "", goal_rate, 100),
    ]
    return '<div class="section-header">Hydration</div>' + _metric_rows(rows)


def _prayer_section(prayer: dict) -> str:
    reminders = int(prayer.get("total_reminders", 0))
    acked = int(prayer.get("acknowledged", 0))
    tahajjud_prayed = int(prayer.get("tahajjud_prayed", 0))
    tahajjud_attempted = int(prayer.get("tahajjud_attempted", 0))

    rows = [
        ("Prayer reminders sent", str(reminders), "this week", reminders, max(reminders, 35)),
        ("Reminders acknowledged", str(acked), f"/ {reminders}", acked, max(reminders, 1)),
        ("Tahajjud prayed", str(tahajjud_prayed), f"/ {tahajjud_attempted} attempts",
         tahajjud_prayed, max(tahajjud_attempted, 7)),
    ]
    return '<div class="section-header">Prayer &amp; Spirituality</div>' + _metric_rows(rows)


def _automations_section(automations: dict) -> str:
    total = int(automations.get("total_triggered", 0))
    types = automations.get("types", [])
    html = '<div class="section-header">Automations</div>'
    html += f"<p><b>{total}</b> automations triggered this week.</p>"
    if types:
        html += f'<p class="types">Types: {", ".join(str(t) for t in types if t)}</p>'
    return html


def _recommendations_section(recommendations: list) -> str:
    html = '<div class="section-header">Recommendations</div>'
    if recommendations:
        html += '<ul class="recs">'
        for rec in recommendations:
            html += f"<li>{rec}</li>"
        html += "</ul>"
    return html


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_html(report: dict[str, Any]) -> str:
    """Return a complete styled HTML document for the weekly health report."""
    period = str(report.get("period", ""))
    generated = str(report.get("generated_at", ""))[:19].replace("T", " ")

    body = (
        "<h1>Weekly Health Report</h1>"
        f'<p class="subtitle">Danah Smart Bed &nbsp;·&nbsp; {period} &nbsp;·&nbsp; Generated {generated}</p>'
        '<hr class="top">'
        + _sleep_section(report.get("sleep", {}))
        + _wellness_section(report.get("wellness", {}))
        + _hydration_section(report.get("hydration", {}))
        + _prayer_section(report.get("prayer", {}))
        + _automations_section(report.get("automations", {}))
        + _recommendations_section(report.get("recommendations", []))
        + f'<div class="footer">Generated by Danah Smart Bed AI &nbsp;·&nbsp; {generated} &nbsp;·&nbsp; Confidential</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Weekly Health Report — Danah Smart Bed</title>
<style>{_CSS}</style>
</head>
<body>{body}</body>
</html>"""


def render_pdf(report: dict[str, Any], output_path: str | Path) -> str:
    """Render report to PDF via WeasyPrint. Returns absolute path string."""
    if not _WEASYPRINT_AVAILABLE:
        raise RuntimeError("weasyprint is not installed — pip install weasyprint")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html_string = render_html(report)
    _wp.HTML(string=html_string).write_pdf(str(output_path))

    logger.info("WeasyPrint weekly report PDF written: %s", output_path)
    return str(output_path.resolve())


def generate_weekly_html_pdf(report: dict[str, Any], output_path: str | Path) -> str:
    """Module-level convenience wrapper around render_pdf()."""
    return render_pdf(report, output_path)