"""Page: many runs at once — parameter sweep, Monte Carlo, optimiser."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from bakbrommer_twin.batch import montecarlo, optimiser, sweep
from bakbrommer_twin.batch.tables import metric_column
from bakbrommer_twin.i18n import t
from bakbrommer_twin.params.types import ParamError
from bakbrommer_twin.reports import batch_figures
from bakbrommer_twin.scenarios.metrics import expected_keys
from bakbrommer_twin.sim.summary import summary_labels
from bakbrommer_twin.ui import batch_common as common
from bakbrommer_twin.ui import state

_SWEEP, _MONTE, _OPTIMUM = "batch_sweep", "batch_monte", "batch_optimum"
_DEFAULT_VARIATIONS = [("mass.rider.mass", 10.0), ("surface.dry_asphalt.friction", 10.0),
                       ("tyre.rolling_resistance_scale", 15.0),
                       ("battery.internal_resistance", 20.0)]
_DEFAULT_SEARCH = [("control.mode_normal.electric_torque", 20.0, 80.0),
                   ("control.vectoring.load_split_gain", 0.0, 6.0)]


def _axis(label: str, key: str, default: str) -> sweep.SweepAxis:
    names = common.numeric_params()
    name = st.selectbox(label, names, names.index(default), format_func=common.param_title,
                        key=f"{key}_param")
    low, high = common.display_range(name)
    now = float(state.working_profile().params.display(name))  # type: ignore[arg-type]
    start_col, stop_col, count_col = st.columns(3)
    start = start_col.number_input(t("batch.from"), low, high, max(low, 0.5 * now),
                                   format="%.6g", key=f"{key}_from_{name}")
    stop = stop_col.number_input(t("batch.to"), low, high, min(high, 1.5 * now or high),
                                 format="%.6g", key=f"{key}_to_{name}")
    count = count_col.number_input(t("batch.steps"), 2, 25, 5, key=f"{key}_count")
    return sweep.SweepAxis(name, sweep.linear_values(start, stop, int(count)))


def _sweep_tab() -> None:
    st.caption(t("batch.sweep_help"))
    scenario = common.pick_scenario("sweep")
    params = state.working_profile().params
    first = _axis(t("batch.first_param"), "sweep_a", "mass.cargo.mass")
    second = None
    if st.checkbox(t("batch.use_second")):
        second = _axis(t("batch.second_param"), "sweep_b",
                       "control.mode_normal.electric_torque")
    limits, workers = common.pick_limits(params, "sweep")
    total = len(first.values) * (len(second.values) if second else 1)
    if st.button(t("batch.run_count", count=total), type="primary", key="sweep_run"):
        bar = st.progress(0.0)
        try:
            table = sweep.run_sweep(params, scenario, first, second, limits, workers,
                                    lambda done, n: bar.progress(done / n))
            st.session_state[_SWEEP] = (table, first.param, second.param if second else None)
        except (ValueError, ParamError) as exc:
            st.error(str(exc))
        bar.empty()
    if _SWEEP not in st.session_state:
        return
    table, param_a, param_b = st.session_state[_SWEEP]
    metrics = common.metric_columns(table, [param_a, param_b or ""])
    metric = st.selectbox(t("batch.metric"), metrics, key="sweep_metric")
    if param_b:
        st.plotly_chart(batch_figures.sweep_heatmap(table, param_a, param_b, metric),
                        width="stretch")
    else:
        st.plotly_chart(batch_figures.sweep_line(table, param_a, metric), width="stretch")
    common.show_table(table, "sweep.csv", "sweep")


def _monte_tab() -> None:
    st.caption(t("batch.monte_help"))
    scenario = common.pick_scenario("monte")
    params = state.working_profile().params
    start = pd.DataFrame({"parameter": [name for name, _ in _DEFAULT_VARIATIONS],
                          "spread_pct": [spread for _, spread in _DEFAULT_VARIATIONS],
                          "distribution": ["normal"] * len(_DEFAULT_VARIATIONS)})
    edited = st.data_editor(start, num_rows="dynamic", width="stretch", key="monte_table",
                            column_config={
                                "parameter": st.column_config.SelectboxColumn(
                                    options=common.numeric_params(), required=True, width="large"),
                                "spread_pct": st.column_config.NumberColumn(min_value=0.1,
                                                                            required=True),
                                "distribution": st.column_config.SelectboxColumn(
                                    options=["normal", "uniform"], required=True)})
    count_col, seed_col = st.columns(2)
    count = count_col.number_input(t("batch.sample_count"), 2, 2000, 20)
    seed = seed_col.number_input(t("batch.seed"), 0, 1_000_000, 1)
    limits, workers = common.pick_limits(params, "monte")
    if st.button(t("batch.run_count", count=int(count)), type="primary", key="monte_run"):
        bar = st.progress(0.0)
        try:
            variations = [montecarlo.Variation(param=row["parameter"],
                                               spread=float(row["spread_pct"]) / 100.0,
                                               distribution=row["distribution"])
                          for row in edited.to_dict("records") if row["parameter"]]
            st.session_state[_MONTE] = montecarlo.run_monte_carlo(
                params, scenario, variations, int(count), int(seed), limits, workers,
                lambda done, n: bar.progress(done / n))
        except (ValueError, ParamError) as exc:
            st.error(str(exc))
        bar.empty()
    if _MONTE not in st.session_state:
        return
    table = st.session_state[_MONTE]
    varied = [c for c in table.columns if "." in c and " [" not in c]
    share = montecarlo.unsafe_share(table)
    st.metric(t("batch.unsafe_share"), f"{share:.0%}")
    if share > 0:
        reasons = table.loc[~table["safe"], "violations"].value_counts()
        st.dataframe(reasons.rename(t("batch.samples")), width="stretch")
    metric = st.selectbox(t("batch.metric"), common.metric_columns(table, varied),
                          key="monte_metric")
    st.plotly_chart(batch_figures.histogram(table, metric), width="stretch")
    with st.expander(t("batch.statistics")):
        st.dataframe(montecarlo.statistics(table), width="stretch")
    common.show_table(table, "monte_carlo.csv", "monte")


def _optimiser_tab() -> None:
    st.caption(t("batch.optimiser_help"))
    scenario = common.pick_scenario("opt")
    profile = state.working_profile()
    params = profile.params
    labels = {**dict(expected_keys(scenario.metrics)), **summary_labels(params)}
    goal_col, direction_col = st.columns([3, 1])
    metric = goal_col.selectbox(t("batch.goal"), list(labels), format_func=lambda k: labels[k])
    directions = {"minimise": "batch.minimise", "maximise": "batch.maximise"}
    direction = direction_col.radio(t("batch.direction"), list(directions),
                                    format_func=lambda d: t(directions[d]))
    start = pd.DataFrame(_DEFAULT_SEARCH, columns=["parameter", "low", "high"])
    edited = st.data_editor(start, num_rows="dynamic", width="stretch", key="opt_table",
                            column_config={"parameter": st.column_config.SelectboxColumn(
                                options=common.numeric_params(), required=True, width="large")})
    size_col, generations_col = st.columns(2)
    population = size_col.number_input(t("batch.population"), 2, 50, 4)
    generations = generations_col.number_input(t("batch.generations"), 1, 200, 4)
    limits, workers = common.pick_limits(params, "opt")
    rows = [row for row in edited.to_dict("records") if row["parameter"]]
    total = int(population) * max(1, len(rows)) * (int(generations) + 1)
    if st.button(t("batch.run_count", count=total), type="primary", key="opt_run"):
        bar = st.progress(0.0)
        try:
            search = [optimiser.SearchParam(param=row["parameter"], low=float(row["low"]),
                                            high=float(row["high"])) for row in rows]
            outcome = optimiser.optimise(
                params, scenario, search, optimiser.Goal(metric=metric, direction=direction),
                limits, optimiser.OptimiserSettings(population=int(population),
                                                    generations=int(generations)),
                workers, lambda done, _: bar.progress(min(1.0, done / total)))
            st.session_state[_OPTIMUM] = (outcome, metric, direction, limits)
        except (ValueError, ParamError) as exc:
            st.error(str(exc))
        bar.empty()
    if _OPTIMUM not in st.session_state:
        return
    outcome, metric, direction, limits = st.session_state[_OPTIMUM]
    unit = outcome.history[0].metric_units[metric]
    column = metric_column(metric, unit)
    st.plotly_chart(batch_figures.optimiser_history(
        [r.metrics.get(metric) for r in outcome.history],
        [not limits.violations(r.metrics) for r in outcome.history],
        direction == "minimise", column), width="stretch")
    if outcome.best is None:
        st.error(t("batch.nothing_safe"))
        if outcome.least_unsafe is not None:
            st.write("; ".join(limits.violations(outcome.least_unsafe.metrics)))
        return
    st.success(t("batch.best_found", runs=outcome.runs))
    st.dataframe(pd.DataFrame({t("table.parameter"): list(outcome.best.overrides),
                               t("table.value"): list(outcome.best.overrides.values())}),
                 hide_index=True)
    if st.button(t("batch.apply")):
        for name, value in outcome.best.overrides.items():
            params.set_display(name, value)
        state.set_working_profile(profile)
        st.toast(t("batch.applied"))


def render() -> None:
    """Draw the page."""
    st.title(t("batch.title"))
    st.write(t("batch.intro"))
    sweep_tab, monte_tab, optimiser_tab = st.tabs(
        [t("batch.tab_sweep"), t("batch.tab_monte"), t("batch.tab_optimiser")])
    with sweep_tab:
        _sweep_tab()
    with monte_tab:
        _monte_tab()
    with optimiser_tab:
        _optimiser_tab()
