"""Shows one run: headline numbers, safety report, charts, animation, export.

Used by the Run page (fresh result) and the Results page (saved result).
"""

from __future__ import annotations

import streamlit as st

from bakbrommer_twin.i18n import t
from bakbrommer_twin.reports import export, tables
from bakbrommer_twin.reports.animation import animation
from bakbrommer_twin.reports.chart_defs import (
    CHARTS,
    CHARTS_BY_KEY,
    DEFAULT_CHARTS,
    charts_for_channels,
)
from bakbrommer_twin.reports.figures import route_map, time_series
from bakbrommer_twin.sim.result import RunResult

_HEADLINE = ("duration", "distance", "max_speed", "consumption_electric", "consumption_fuel",
             "min_rollover_margin")
_ANIMATION_FRAMES = 240
# channel used as horizontal axis -> translation key of its name
AXIS_LABELS = {"time": "result.axis_time", "distance": "result.axis_distance"}


def _headline(result: RunResult) -> None:
    meta = result.meta
    st.caption(f"{meta.scenario_name} · {meta.profile_name or '—'} · {meta.controller} · "
               f"{t('end.' + meta.end_reason)}")
    if not meta.validated:
        st.warning(t("app.not_validated"))
    shown = [*meta.metrics, *(m for m in meta.summary if m.key in _HEADLINE)]
    for start in range(0, len(shown), 4):
        for column, metric in zip(st.columns(4), shown[start:start + 4], strict=False):
            unit = "" if metric.unit == "-" else f" {metric.unit}"
            column.metric(metric.label, f"{tables.format_value(metric.display())}{unit}")


def _safety(result: RunResult) -> None:
    events = result.meta.events
    st.subheader(t("result.safety_title", count=len(events)))
    if not events:
        st.success(t("report.no_events"))
        return
    if any(event.kind == "rollover" for event in events):
        st.error(t("result.rolled_over"))
    st.dataframe(tables.events_table(result), hide_index=True, width="stretch")


def _charts(result: RunResult, key: str) -> None:
    left, right = st.columns([3, 1])
    chosen = left.multiselect(
        t("result.charts_pick"), [chart.key for chart in CHARTS], default=list(DEFAULT_CHARTS),
        format_func=lambda k: t(f"chart.{k}"), key=f"{key}_charts")
    axis = right.radio(t("result.x_axis"), list(AXIS_LABELS), horizontal=True,
                       format_func=lambda name: t(AXIS_LABELS[name]), key=f"{key}_axis")
    labels = {item.name: f"{item.label} [{item.unit}]" for item in result.meta.channels}
    extra = st.multiselect(t("result.channels_pick"), list(labels), key=f"{key}_channels",
                           format_func=lambda name: labels[name])
    charts = [CHARTS_BY_KEY[k] for k in chosen] + charts_for_channels(result, extra)
    if charts:
        st.plotly_chart(time_series([result], charts, axis), width="stretch")
    else:
        st.info(t("result.no_charts"))


def _export(result: RunResult, key: str) -> None:
    """Three download buttons; each file is only built when its button is pressed."""
    st.caption(t("result.export_intro"))
    csv_col, html_col, pdf_col = st.columns(3)
    name = export.file_stem(result)
    csv_col.download_button(t("result.export_csv"), lambda: export.csv_text(result),
                            f"{name}.csv", "text/csv", key=f"{key}_csv", width="stretch")
    html_col.download_button(t("result.download_html"), lambda: export.html_report(result),
                             f"{name}.html", "text/html", key=f"{key}_html", width="stretch")
    pdf_col.download_button(t("result.download_pdf"), lambda: export.pdf_report(result),
                            f"{name}.pdf", "application/pdf", key=f"{key}_pdf",
                            width="stretch")


def render_result(result: RunResult, key: str = "result") -> None:
    """Draw everything about one run. ``key`` keeps widget states of two views apart."""
    st.header(result.meta.name)
    _headline(result)
    _safety(result)
    charts, moving, route, numbers, files = st.tabs([
        t("result.tab_charts"), t("result.tab_animation"), t("result.tab_route"),
        t("result.tab_numbers"), t("result.tab_export")])
    with charts:
        _charts(result, key)
    with moving:
        st.caption(t("result.animation_help"))
        follow = st.toggle(t("result.follow"), value=True, key=f"{key}_follow")
        if st.toggle(t("result.show_animation"), value=False, key=f"{key}_animate"):
            st.plotly_chart(animation(result, _ANIMATION_FRAMES, follow), width="stretch")
    with route:
        st.plotly_chart(route_map([result]), width="stretch")
    with numbers:
        st.dataframe(tables.metrics_table(result.meta.summary), hide_index=True, width="stretch")
    with files:
        _export(result, key)
