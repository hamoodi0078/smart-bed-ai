"""Weekly health report PDF generator powered by ReportLab.

Public API
----------
WeeklyReportPDF.build(report, output_path) -> str
    Renders a WeeklyHealthReport dict to a styled A4 PDF.
    Returns the absolute path of the written file.

generate_weekly_pdf(report, output_path) -> str
    Module-level convenience wrapper.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("reports.pdf_generator")

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False

# Brand palette
_BRAND_TEAL = colors.HexColor("#1A7F8E") if _REPORTLAB_AVAILABLE else None
_BRAND_DARK = colors.HexColor("#1C2B36") if _REPORTLAB_AVAILABLE else None
_BRAND_LIGHT = colors.HexColor("#EAF6F8") if _REPORTLAB_AVAILABLE else None
_BRAND_ACCENT = colors.HexColor("#F4A261") if _REPORTLAB_AVAILABLE else None
_GREY = colors.HexColor("#6B7280") if _REPORTLAB_AVAILABLE else None
_WHITE = colors.white if _REPORTLAB_AVAILABLE else None


def _styles():
    base = getSampleStyleSheet()

    def _add(name, **kwargs):
        if name not in base.byName:
            base.add(ParagraphStyle(name=name, **kwargs))
        return base[name]

    _add("ReportTitle",
         fontSize=22, leading=28, textColor=_BRAND_DARK,
         fontName="Helvetica-Bold", spaceAfter=4)
    _add("ReportSubtitle",
         fontSize=11, leading=16, textColor=_GREY,
         fontName="Helvetica", spaceAfter=12)
    _add("SectionHeader",
         fontSize=13, leading=18, textColor=_WHITE,
         fontName="Helvetica-Bold", spaceAfter=6,
         backColor=_BRAND_TEAL, leftIndent=6, rightIndent=6,
         borderPadding=(4, 6, 4, 6))
    _add("MetricLabel",
         fontSize=9, leading=13, textColor=_GREY,
         fontName="Helvetica")
    _add("MetricValue",
         fontSize=11, leading=15, textColor=_BRAND_DARK,
         fontName="Helvetica-Bold")
    _add("BulletItem",
         fontSize=10, leading=14, textColor=_BRAND_DARK,
         fontName="Helvetica", leftIndent=12, spaceAfter=3,
         bulletText="•")
    _add("Footer",
         fontSize=8, leading=11, textColor=_GREY,
         fontName="Helvetica", alignment=TA_CENTER)
    _add("ScoreGood",
         fontSize=13, leading=17, textColor=colors.HexColor("#16A34A"),
         fontName="Helvetica-Bold")
    _add("ScoreWarn",
         fontSize=13, leading=17, textColor=colors.HexColor("#D97706"),
         fontName="Helvetica-Bold")
    _add("ScoreBad",
         fontSize=13, leading=17, textColor=colors.HexColor("#DC2626"),
         fontName="Helvetica-Bold")

    return base


def _score_style(styles, value: float, good_above: float, bad_below: float):
    if value >= good_above:
        return styles["ScoreGood"]
    if value <= bad_below:
        return styles["ScoreBad"]
    return styles["ScoreWarn"]


def _bar(value: float, max_value: float, width: float = 200, height: float = 10) -> Table:
    """Render a simple horizontal progress bar using a two-cell Table."""
    ratio = min(1.0, max(0.0, value / max_value)) if max_value else 0.0
    filled = width * ratio
    empty = width - filled
    fill_color = _BRAND_TEAL if ratio >= 0.6 else (_BRAND_ACCENT if ratio >= 0.3 else colors.HexColor("#DC2626"))
    data = [["", ""]]
    col_widths = [filled, empty] if filled > 0 else [0.1, width - 0.1]
    t = Table(data, colWidths=col_widths, rowHeights=[height])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), fill_color),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#E5E7EB")),
        ("GRID", (0, 0), (-1, -1), 0, colors.white),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


def _metric_row(label: str, value: str, sublabel: str = "") -> list:
    """Three-column metric row: label | bar placeholder | value."""
    return [label, sublabel, value]


class WeeklyReportPDF:
    """Render a WeeklyHealthReport dict to a styled A4 PDF."""

    PAGE_W, PAGE_H = A4
    MARGIN = 1.8 * cm

    def build(self, report: dict[str, Any], output_path: str | Path) -> str:
        """Write the PDF to *output_path* and return the absolute path string."""
        if not _REPORTLAB_AVAILABLE:
            raise RuntimeError("reportlab is not installed — pip install reportlab")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=self.MARGIN,
            rightMargin=self.MARGIN,
            topMargin=self.MARGIN,
            bottomMargin=self.MARGIN,
            title="Weekly Health Report — Danah Smart Bed",
            author="Danah AI",
        )

        styles = _styles()
        story: list[Any] = []

        self._add_header(story, styles, report)
        self._add_sleep_section(story, styles, report.get("sleep", {}))
        self._add_wellness_section(story, styles, report.get("wellness", {}))
        self._add_hydration_section(story, styles, report.get("hydration", {}))
        self._add_prayer_section(story, styles, report.get("prayer", {}))
        self._add_automations_section(story, styles, report.get("automations", {}))
        self._add_recommendations(story, styles, report.get("recommendations", []))
        self._add_footer(story, styles, report)

        doc.build(story)
        logger.info("Weekly health report PDF written: %s", output_path)
        return str(output_path.resolve())

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _add_header(self, story, styles, report):
        story.append(Paragraph("Danah Smart Bed", styles["ReportSubtitle"]))
        story.append(Paragraph("Weekly Health Report", styles["ReportTitle"]))
        period = str(report.get("period", ""))
        generated = str(report.get("generated_at", ""))[:10]
        story.append(Paragraph(f"{period}  ·  Generated {generated}", styles["ReportSubtitle"]))
        story.append(HRFlowable(width="100%", thickness=1.5, color=_BRAND_TEAL, spaceAfter=12))

    def _section_header(self, story, styles, title: str):
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"  {title}", styles["SectionHeader"]))
        story.append(Spacer(1, 6))

    def _metrics_table(self, rows: list[tuple[str, Any, str]], bar_maxes: list[float]) -> Table:
        """Build a metrics table from (label, value, unit) tuples with progress bars."""
        usable_w = self.PAGE_W - 2 * self.MARGIN
        col_w = [usable_w * 0.34, usable_w * 0.40, usable_w * 0.26]

        data = []
        for i, (label, value, unit) in enumerate(rows):
            bar_max = bar_maxes[i] if i < len(bar_maxes) else 1.0
            try:
                num_val = float(str(value).replace("%", "").replace("h", "").strip())
            except Exception:
                num_val = 0.0
            data.append([
                Paragraph(label, getSampleStyleSheet()["Normal"]),
                _bar(num_val, bar_max, width=usable_w * 0.38, height=9),
                Paragraph(f"<b>{value}</b> {unit}", getSampleStyleSheet()["Normal"]),
            ])

        t = Table(data, colWidths=col_w, rowHeights=[22] * len(data))
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0, colors.white),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_BRAND_LIGHT, colors.white]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        return t

    def _add_sleep_section(self, story, styles, sleep: dict):
        self._section_header(story, styles, "Sleep")
        avg = float(sleep.get("avg_hours", 0))
        target = float(sleep.get("target_hours", 8))
        consistency = float(sleep.get("consistency_score", 0))
        debt = float(sleep.get("total_debt_hours", 0))
        nights = int(sleep.get("nights_tracked", 0))
        short = int(sleep.get("short_nights", 0))

        rows = [
            ("Average sleep", f"{avg:.1f}h", f"/ {target:.0f}h target"),
            ("Consistency score", f"{consistency:.0f}", "/ 100"),
            ("Sleep debt", f"{debt:.1f}h", "this week"),
            ("Nights tracked", str(nights), "nights"),
            ("Short nights (<6h)", str(short), "nights"),
        ]
        bar_maxes = [target or 8, 100, max(debt, 5), 7, 7]
        story.append(self._metrics_table(rows, bar_maxes))

    def _add_wellness_section(self, story, styles, wellness: dict):
        self._section_header(story, styles, "Wellness & Stress")
        avg_stress = float(wellness.get("avg_stress_score", 0))
        high_stress = int(wellness.get("high_stress_days", 0))
        overthinking = int(wellness.get("overthinking_entries", 0))
        trend = str(wellness.get("stress_trend", "stable")).capitalize()

        rows = [
            ("Average stress level", f"{avg_stress:.0f}", "/ 100"),
            ("High-stress days", str(high_stress), "days"),
            ("Overthinking entries", str(overthinking), "entries"),
        ]
        bar_maxes = [100, 7, 10]
        story.append(self._metrics_table(rows, bar_maxes))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Stress trend: <b>{trend}</b>", styles["MetricLabel"]))

    def _add_hydration_section(self, story, styles, hydration: dict):
        self._section_header(story, styles, "Hydration")
        days = int(hydration.get("days_tracked", 0))
        avg_ml = int(hydration.get("avg_ml", 0))
        goals_met = int(hydration.get("goals_met", 0))
        goal_rate = float(hydration.get("goal_rate_pct", 0))

        rows = [
            ("Average daily intake", f"{avg_ml}", "ml / day"),
            ("Goals met", f"{goals_met}", f"/ {days} days"),
            ("Goal achievement", f"{goal_rate:.0f}%", ""),
        ]
        bar_maxes = [3000, days or 7, 100]
        story.append(self._metrics_table(rows, bar_maxes))

    def _add_prayer_section(self, story, styles, prayer: dict):
        self._section_header(story, styles, "Prayer & Spirituality")
        reminders = int(prayer.get("total_reminders", 0))
        acked = int(prayer.get("acknowledged", 0))
        tahajjud_prayed = int(prayer.get("tahajjud_prayed", 0))
        tahajjud_attempted = int(prayer.get("tahajjud_attempted", 0))

        rows = [
            ("Prayer reminders sent", str(reminders), "this week"),
            ("Reminders acknowledged", str(acked), f"/ {reminders}"),
            ("Tahajjud prayed", str(tahajjud_prayed), f"/ {tahajjud_attempted} attempts"),
        ]
        bar_maxes = [max(reminders, 35), max(reminders, 1), max(tahajjud_attempted, 7)]
        story.append(self._metrics_table(rows, bar_maxes))

    def _add_automations_section(self, story, styles, automations: dict):
        self._section_header(story, styles, "Automations")
        total = int(automations.get("total_triggered", 0))
        types = automations.get("types", [])

        story.append(Paragraph(
            f"<b>{total}</b> automations triggered this week.",
            styles["MetricLabel"],
        ))
        if types:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                "Types: " + ", ".join(str(t) for t in types if t),
                styles["MetricLabel"],
            ))

    def _add_recommendations(self, story, styles, recommendations: list):
        self._section_header(story, styles, "Recommendations")
        for rec in recommendations:
            story.append(Paragraph(str(rec), styles["BulletItem"]))

    def _add_footer(self, story, styles, report):
        story.append(Spacer(1, 16))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY, spaceAfter=6))
        generated = str(report.get("generated_at", ""))[:19].replace("T", " ")
        story.append(Paragraph(
            f"Generated by Danah Smart Bed AI  ·  {generated}  ·  Confidential",
            styles["Footer"],
        ))


def generate_weekly_pdf(report: dict[str, Any], output_path: str | Path) -> str:
    """Module-level convenience wrapper around WeeklyReportPDF.build()."""
    return WeeklyReportPDF().build(report, output_path)