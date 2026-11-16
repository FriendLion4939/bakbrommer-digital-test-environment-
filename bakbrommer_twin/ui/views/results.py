"""Page: saved runs — open one, compare several, delete."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from bakbrommer_twin.i18n import t
from bakbrommer_twin.reports import tables
from bakbrommer_twin.reports.chart_defs import CHARTS, CHARTS_BY_KEY, DEFAULT_CHARTS
from bakbrommer_twin.reports.figures import route_map, time_series
from bakbrommer_twin.sim.result import RunResult
from bakbrommer_twin.ui import state
from bakbrommer_twin.ui.result_view import AXIS_LABELS, render_result

_MAX_COMPARED = 4  # runs in one comparison (line styles stay distinguishable)


def _run_list(folders: list[Path]) -> pd.DataFrame:
    runs = [state.load_run(folder) for folder in folders]
    return pd.DataFrame({
        t("results.col_name"): [r.meta.name for r in runs],
        t("results.col_scenario"): [r.meta.scenario_name for r in runs],
        t("results.col_profile"): [r.meta.profile_name for r in runs],
        t("results.col_when"): [r.meta.created.replace("T", " ") for r in runs],
        t("results.col_end"): [t("end." + r.meta.end_reason) for r in runs],
        t("results.col_events"): [len(r.meta.events) for r in runs],
    })


def _highlight(row: pd.Series[Any]) -> list[str]:
    return ["background-color: #fff4d6" if row["notable"] else ""] * len(row)


def _compare(runs: list[RunResult]) -> None:
    st.header(t("results.compare_title", count=len(runs)))
    st.caption(t("results.compare_help"))
    table = tables.comparison_table(runs)
    only_changed = st.toggle(t("results.only_changed"), value=False)
    shown = table[table["notable"]] if only_changed else table
    st.dataframe(shown.style.apply(_highlight, axis=1), hide_index=True, width="stretch",
                 column_config={"notable": None})
    changed = tables.parameter_differences(runs)
    with st.expander(t("results.param_differences", count=len(changed))):
        st.dataframe(changed, hide_index=True, width="stretch")
    left, right = st.columns([3, 1])
    chosen = left.multiselect(t("result.charts_pick"), [c.key for c in CHARTS],
                              default=list(DEFAULT_CHARTS[:3]),
                              format_func=lambda k: t(f"chart.{k}"), key="compare_charts")
    axis = right.radio(t("result.x_axis"), list(AXIS_LABELS), horizontal=True,
                       format_func=lambda name: t(AXIS_LABELS[name]), key="compare_axis")
    if chosen:
        st.plotly_chart(time_series(runs, [CHARTS_BY_KEY[k] for k in chosen], axis),
                        width="stretch")
    st.plotly_chart(route_map(runs), width="stretch")


def render() -> None:
    """Draw the page."""
    st.title(t("results.title"))
    folders = state.saved_runs()
    if not folders:
        st.info(t("results.none"))
        return
    st.write(t("results.intro"))
    picked = st.dataframe(_run_list(folders), hide_index=True, width="stretch",
                          on_select="rerun", selection_mode="multi-row", key="results_table")
    rows: list[int] = list(picked["selection"]["rows"])
    if not rows:
        st.caption(t("results.pick_hint"))
        return
    chosen = [folders[i] for i in rows]
    with st.popover(t("results.delete", count=len(chosen))):
        if st.button(t("results.delete_confirm")):
            for folder in chosen:
                shutil.rmtree(folder)
            st.rerun()
    if len(chosen) == 1:
        render_result(state.load_run(chosen[0]), key="saved")
    else:
        if len(chosen) > _MAX_COMPARED:
            st.warning(t("results.too_many", limit=_MAX_COMPARED))
        _compare([state.load_run(folder) for folder in chosen[:_MAX_COMPARED]])
