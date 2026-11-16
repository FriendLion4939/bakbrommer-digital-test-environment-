"""Controls shared by the three batch tools (scenario, limits, workers, tables)."""

from __future__ import annotations

from typing import Any, cast

import pandas as pd
import streamlit as st

from bakbrommer_twin.batch.constraints import SafetyConstraints
from bakbrommer_twin.batch.runner import default_workers
from bakbrommer_twin.i18n import param_label, t
from bakbrommer_twin.params import REGISTRY, units
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.types import Kind
from bakbrommer_twin.scenarios.scenario import Scenario
from bakbrommer_twin.ui import state

_NOT_METRICS = ("run", "end_reason", "safe", "violations")


def numeric_params() -> list[str]:
    """Names of all parameters that hold a plain number."""
    return [d.name for d in REGISTRY if d.kind in (Kind.NUMBER, Kind.INTEGER)]


def param_title(name: str) -> str:
    """``Label [unit] (name)`` for parameter pickers."""
    definition = REGISTRY.get(name)
    unit = f" [{definition.unit}]" if definition.unit else ""
    return f"{param_label(definition)}{unit} — {name}"


def display_range(name: str) -> tuple[float, float]:
    """Allowed range of a parameter in its friendly unit."""
    d = REGISTRY.get(name)
    return (units.from_si(cast(float, d.min), d.unit), units.from_si(cast(float, d.max), d.unit))


def pick_scenario(key: str) -> Scenario:
    """Scenario picker; returns the chosen scenario."""
    store = state.scenario_store()
    library = {k: store.load(k) for k in store.list_keys()}
    chosen = st.selectbox(t("run.scenario"), sorted(library), key=f"{key}_scenario",
                          format_func=lambda k: f"[{library[k].category}] {library[k].name}")
    return library[chosen]


def pick_limits(params: ParamSet, key: str) -> tuple[SafetyConstraints, int]:
    """Safety limits and number of parallel workers, in an expander."""
    base = SafetyConstraints.from_params(params)
    with st.expander(t("batch.limits_title")):
        st.caption(t("batch.limits_help"))
        a, b, c, d = st.columns(4)
        lifts = a.number_input(t("batch.max_lift_events"), 0, 1000, base.max_wheel_lift_events,
                               key=f"{key}_lifts")
        height = b.number_input(t("batch.max_lift_height"), 0.0, 1000.0,
                                units.from_si(base.max_wheel_lift, "mm"), key=f"{key}_height")
        current = c.number_input(t("batch.max_current"), 1.0, 500.0, base.max_battery_current,
                                 key=f"{key}_current")
        margin = d.number_input(t("batch.min_margin"), 0.0, 1.0, base.min_rollover_margin, 0.05,
                                key=f"{key}_margin")
        workers = st.slider(t("batch.workers"), 1, max(2, default_workers() + 1),
                            default_workers(), key=f"{key}_workers", help=t("batch.workers_help"))
    limits = base.model_copy(update={
        "max_wheel_lift_events": int(lifts), "max_wheel_lift": units.to_si(height, "mm"),
        "max_battery_current": float(current), "min_rollover_margin": float(margin)})
    return limits, int(workers)


def metric_columns(table: pd.DataFrame, params: list[str]) -> list[str]:
    """Columns of a results table that are metrics (numeric results)."""
    skip = {*_NOT_METRICS, *params, "sim.random_seed"}
    return [c for c in table.columns
            if c not in skip and pd.api.types.is_numeric_dtype(table[c])]


def show_table(table: pd.DataFrame, file_name: str, key: str) -> None:
    """Results table with unsafe rows tinted, plus a CSV download."""
    def tint(row: pd.Series[Any]) -> list[str]:
        return ["" if row["safe"] else "background-color: #fde4e4"] * len(row)

    st.dataframe(table.style.apply(tint, axis=1), hide_index=True, width="stretch")
    st.download_button(t("result.export_csv"), table.to_csv(index=False), file_name, "text/csv",
                       key=f"{key}_download")
