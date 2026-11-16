"""Page: import a ride log, clean it, replay it in the simulator, try "what if"."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from bakbrommer_twin import paths
from bakbrommer_twin.data_import import can_log, clean
from bakbrommer_twin.data_import.channels import LOG_CHANNELS
from bakbrommer_twin.data_import.recording import Recording
from bakbrommer_twin.data_import.replay import fit_quality, quality_table_rows, replay
from bakbrommer_twin.i18n import t
from bakbrommer_twin.params.types import ParamError
from bakbrommer_twin.reports import tables
from bakbrommer_twin.reports.chart_defs import ChartDef
from bakbrommer_twin.reports.figures import time_series
from bakbrommer_twin.sim.result import RunResult
from bakbrommer_twin.ui import batch_common, import_steps, state

RECORDING = "import_recording"  # session key of the cleaned recording
_BASE, _WHAT_IF = "replay_base", "replay_what_if"
_DEFAULT_OVERLAY = ("vehicle_speed", "battery_current", "gyro_z", "accel_x")


def _clean_step(raw_key: str) -> Recording | None:
    raw = st.session_state.get(raw_key)
    if raw is None:
        return None
    rate_col, gap_col, filter_col = st.columns(3)
    rate = rate_col.number_input(t("import.rate"), 5.0, 1000.0, 100.0)
    gap = gap_col.number_input(t("import.gap"), 0.05, 60.0, 0.5)
    cutoff = filter_col.number_input(t("import.lowpass"), 0.0, 500.0, 0.0,
                                     help=t("import.lowpass_help"))
    try:
        recording, report = clean.clean(raw, clean.CleanOptions(
            rate_hz=rate, gap_s=gap, lowpass_hz=cutoff or None))
    except (ValueError, ValidationError) as exc:
        st.error(str(exc))
        return None
    for note in recording.notes:
        st.caption(f"• {note}")
    st.dataframe(pd.DataFrame({
        t("import.col_channel"): [LOG_CHANNELS[q.channel].title for q in report],
        t("import.col_samples"): [q.samples for q in report],
        t("import.col_rate"): [round(q.rate, 1) for q in report],
        t("import.col_rejected"): [q.rejected for q in report],
        t("import.col_gaps"): [q.gaps for q in report],
        t("import.col_longest_gap"): [round(q.longest_gap, 2) for q in report],
        t("import.col_coverage"): [round(100 * q.coverage, 1) for q in report],
    }), hide_index=True, width="stretch")
    st.caption(t("import.duration", seconds=recording.duration))
    name_col, save_col = st.columns([3, 1])
    key = name_col.text_input(t("import.recording_name"), "")
    if save_col.button(t("import.recording_save"), disabled=not key, width="stretch"):
        try:
            recording.save(paths.recordings_dir(), key)
            st.toast(t("import.recording_saved"))
        except ValueError as exc:
            st.error(str(exc))
    return recording


def _overlay(results: list[RunResult], channels: list[str]) -> None:
    charts = [ChartDef(f"custom_{i}", (LOG_CHANNELS[name].sim_channel, f"meas_{name}"))
              for i, name in enumerate(channels)]
    if charts:
        st.plotly_chart(time_series(results, charts), width="stretch")


def _replay_step(recording: Recording) -> None:
    profile = state.working_profile()
    st.caption(t("import.replay_help", profile=profile.name))
    if "throttle" not in recording.data:
        st.warning(t("import.replay_needs_throttle"))
        return
    if st.button(t("import.replay_run"), type="primary"):
        bar = st.progress(0.0)
        st.session_state[_BASE] = replay(
            profile.params, recording, name=t("import.replay_name", source=recording.source),
            profile_name=profile.name, validated=profile.validated, progress=bar.progress)
        st.session_state.pop(_WHAT_IF, None)
        bar.empty()
    base: RunResult | None = st.session_state.get(_BASE)
    if base is None:
        return
    if recording.synthetic:
        st.info(t("import.synthetic_note"))
    available = [name for name in recording.data if LOG_CHANNELS[name].sim_channel in base.data]
    shown = st.multiselect(
        t("import.overlay_channels"), available,
        default=[name for name in _DEFAULT_OVERLAY if name in available],
        format_func=lambda name: LOG_CHANNELS[name].title)
    what_if: RunResult | None = st.session_state.get(_WHAT_IF)
    _overlay([base, what_if] if what_if is not None else [base], shown)
    st.subheader(t("import.fit_title"))
    st.caption(t("import.fit_help"))
    st.dataframe(pd.DataFrame(quality_table_rows(fit_quality(base))), hide_index=True,
                 width="stretch")

    st.subheader(t("import.what_if_title"))
    st.caption(t("import.what_if_help"))
    start = pd.DataFrame({"parameter": ["control.mode_normal.electric_torque"], "value": [60.0]})
    edited = st.data_editor(start, num_rows="dynamic", width="stretch", key="what_if_table",
                            column_config={"parameter": st.column_config.SelectboxColumn(
                                options=batch_common.numeric_params(), required=True,
                                width="large")})
    if st.button(t("import.what_if_run")):
        overrides = {row["parameter"]: float(row["value"])
                     for row in edited.to_dict("records") if row["parameter"]}
        try:
            st.session_state[_WHAT_IF] = replay(
                profile.params, recording, name=t("import.what_if_name"),
                profile_name=profile.name, validated=profile.validated, overrides=overrides)
            st.rerun()
        except (ValueError, ParamError) as exc:
            st.error(str(exc))
    if what_if is not None:
        table = tables.comparison_table([base, what_if])
        st.dataframe(table[table["notable"]].drop(columns="notable"), hide_index=True,
                     width="stretch")


def render() -> None:
    """Draw the page."""
    st.title(t("import.title"))
    st.write(t("import.intro"))
    st.header(t("import.step_file"))
    picked = import_steps.pick_file()
    if picked is None:
        st.info(t("import.pick_first"))
        return
    name, text, synthetic = picked
    st.header(t("import.step_read"))
    is_can = can_log.detect_format(text) != "unknown"
    raw = import_steps.read_can(name, text) if is_can else import_steps.read_csv(name, text)
    if raw is None:
        return
    raw.synthetic = synthetic
    st.session_state["import_raw"] = raw
    st.header(t("import.step_clean"))
    recording = _clean_step("import_raw")
    if recording is None:
        return
    st.session_state[RECORDING] = recording
    st.header(t("import.step_replay"))
    _replay_step(recording)
