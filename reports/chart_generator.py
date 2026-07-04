"""Plotly chart generators for Smart Bed AI analytics.

Each function accepts a data dict/list from AnalyticsEngine and returns a
Plotly figure serialised as a JSON-serialisable dict (via fig.to_dict()).
Pass the result straight to the frontend or embed via plotly.js.

Public API
----------
sleep_trend_chart(trend_data)           -> dict
daily_activity_chart(daily_data)        -> dict
automation_effectiveness_chart(data)    -> dict
feature_adoption_chart(adoption_data)   -> dict
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("reports.chart_generator")

try:
    import plotly.graph_objects as go
    import plotly.express as px

    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False

# Brand palette kept consistent with pdf_generator.py
_TEAL = "#1A7F8E"
_DARK = "#1C2B36"
_ACCENT = "#F4A261"
_LIGHT = "#EAF6F8"
_GREY = "#6B7280"
_GREEN = "#16A34A"
_RED = "#DC2626"

_LAYOUT_BASE: dict[str, Any] = {
    "paper_bgcolor": "white",
    "plot_bgcolor": _LIGHT,
    "font": {"family": "Inter, Helvetica, Arial, sans-serif", "color": _DARK},
    "margin": {"l": 40, "r": 20, "t": 50, "b": 40},
    "legend": {"bgcolor": "rgba(0,0,0,0)", "borderwidth": 0},
}


def _check() -> None:
    if not _PLOTLY_AVAILABLE:
        raise RuntimeError("plotly is not installed — pip install plotly")


# ---------------------------------------------------------------------------
# Sleep trend — line chart
# ---------------------------------------------------------------------------


def sleep_trend_chart(trend_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Line chart: sleep hours and sleep score per night.

    trend_data: list of {date, sleep_score, total_hours, quality_rating}
    as returned by AnalyticsEngine.sleep_trend().
    """
    _check()

    dates = [d.get("date", "") for d in trend_data]
    hours = [d.get("total_hours") for d in trend_data]
    scores = [d.get("sleep_score") for d in trend_data]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=hours,
            name="Hours slept",
            mode="lines+markers",
            line={"color": _TEAL, "width": 2},
            marker={"size": 6, "color": _TEAL},
            yaxis="y1",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=scores,
            name="Sleep score",
            mode="lines+markers",
            line={"color": _ACCENT, "width": 2, "dash": "dot"},
            marker={"size": 6, "color": _ACCENT},
            yaxis="y2",
        )
    )

    # 7-hour recommended minimum reference line
    fig.add_hline(
        y=7,
        line_dash="dash",
        line_color=_GREY,
        opacity=0.5,
        annotation_text="7h target",
        annotation_position="bottom right",
    )

    layout = dict(_LAYOUT_BASE)
    layout.update(
        {
            "title": {"text": "Sleep Trend", "font": {"size": 16, "color": _DARK}},
            "xaxis": {"title": "Date", "showgrid": False},
            "yaxis": {"title": "Hours", "range": [0, 12], "gridcolor": "#E5E7EB"},
            "yaxis2": {
                "title": "Score",
                "range": [0, 100],
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
            },
        }
    )
    fig.update_layout(**layout)
    return fig.to_dict()


# ---------------------------------------------------------------------------
# Daily activity — bar chart
# ---------------------------------------------------------------------------


def daily_activity_chart(daily_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Bar chart: total events per day.

    daily_data: list of {date, events} as returned by
    AnalyticsEngine.daily_active_events().
    """
    _check()

    dates = [d.get("date", "") for d in daily_data]
    counts = [d.get("events", 0) for d in daily_data]

    fig = go.Figure(
        go.Bar(
            x=dates,
            y=counts,
            marker_color=_TEAL,
            name="Events",
        )
    )

    layout = dict(_LAYOUT_BASE)
    layout.update(
        {
            "title": {"text": "Daily Activity", "font": {"size": 16, "color": _DARK}},
            "xaxis": {"title": "Date", "showgrid": False},
            "yaxis": {"title": "Events", "gridcolor": "#E5E7EB"},
            "bargap": 0.3,
        }
    )
    fig.update_layout(**layout)
    return fig.to_dict()


# ---------------------------------------------------------------------------
# Automation effectiveness — donut chart
# ---------------------------------------------------------------------------


def automation_effectiveness_chart(data: dict[str, Any]) -> dict[str, Any]:
    """Donut chart: automation accepted vs declined.

    data: dict with keys total_accepted, total_declined, acceptance_rate, period_days
    as returned by AnalyticsEngine.automation_effectiveness().
    """
    _check()

    accepted = int(data.get("total_accepted", 0))
    declined = int(data.get("total_declined", 0))
    rate = float(data.get("acceptance_rate", 0))
    period = int(data.get("period_days", 30))

    labels = ["Accepted", "Declined"]
    values = [accepted, declined]
    colors = [_GREEN, _RED]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker={"colors": colors},
            textinfo="label+percent",
            hovertemplate="%{label}: %{value}<extra></extra>",
        )
    )

    fig.add_annotation(
        text=f"{rate:.0f}%<br>accepted",
        x=0.5,
        y=0.5,
        font={"size": 14, "color": _DARK, "family": "Helvetica-Bold"},
        showarrow=False,
    )

    layout = dict(_LAYOUT_BASE)
    layout.update(
        {
            "title": {
                "text": f"Automation Effectiveness — last {period} days",
                "font": {"size": 16, "color": _DARK},
            },
            "showlegend": True,
        }
    )
    fig.update_layout(**layout)
    return fig.to_dict()


# ---------------------------------------------------------------------------
# Feature adoption — horizontal bar chart
# ---------------------------------------------------------------------------


def feature_adoption_chart(adoption_data: dict[str, Any]) -> dict[str, Any]:
    """Horizontal bar chart: usage count per feature.

    adoption_data: dict with keys usage_counts, adoption_rate, features
    as returned by AnalyticsEngine.feature_adoption().
    """
    _check()

    usage: dict[str, int] = adoption_data.get("usage_counts", {})
    features_adopted: dict[str, bool] = adoption_data.get("features", {})

    # sort descending by usage count
    sorted_features = sorted(usage.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k.replace("_", " ").title() for k, _ in sorted_features]
    counts = [v for _, v in sorted_features]
    bar_colors = [_TEAL if features_adopted.get(k, False) else _GREY for k, _ in sorted_features]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color=bar_colors,
            name="Usage",
        )
    )

    adoption_rate = float(adoption_data.get("adoption_rate", 0))
    layout = dict(_LAYOUT_BASE)
    layout.update(
        {
            "title": {
                "text": f"Feature Adoption — {adoption_rate:.0f}% of features used",
                "font": {"size": 16, "color": _DARK},
            },
            "xaxis": {"title": "Total uses", "gridcolor": "#E5E7EB"},
            "yaxis": {"showgrid": False},
            "bargap": 0.25,
            "height": max(300, len(labels) * 35 + 120),
        }
    )
    fig.update_layout(**layout)
    return fig.to_dict()
