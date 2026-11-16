"""Page: fit uncertain parameters to a recorded ride and accept them into the profile."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from bakbrommer_twin import paths
from bakbrommer_twin.calibration.fit import (
    SUGGESTED_PARAMS,
    SUGGESTED_TARGETS,
    CalibrationResult,
    accept,
    calibrate,
)
from bakbrommer_twin.data_import.channels import LOG_CHANNELS
from bakbrommer_twin.data_import.recording import Recording, list_recordings
from bakbrommer_twin.data_import.replay import quality_table_rows
from bakbrommer_twin.i18n import t
from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.types import Kind, ParamError
from bakbrommer_twin.ui import batch_common, state
from bakbrommer_twin.ui.views.import_replay import RECORDING

_RESULT = "calibration_result"
_SESSION = "__session__"


def _pick_recording() -> Recording | None:
    saved = list_recordings(paths.recordings_dir())
    options = ([_SESSION] if RECORDING in st.session_state else []) + saved
    if not options:
        st.info(t("calibration.no_recording"))
        return None
    chosen = st.selectbox(t("calibration.recording"), options,
                          format_func=lambda k: t("calibration.session_recording")
                          if k == _SESSION else k)
    if chosen == _SESSION:
        recording: Recording = st.session_state[RECORDING]
        return recording
    return Recording.load(paths.recordings_dir() / chosen)


def _show(result: CalibrationResult, recording: Recording) -> None:
    st.subheader(t("calibration.values_title"))
    st.dataframe(pd.DataFrame({
        t("table.parameter"): [batch_common.param_title(name) for name in result.fitted],
        t("calibration.before"): list(result.start.values()),
        t("calibration.after"): list(result.fitted.values()),
    }), hide_index=True, width="stretch")
    st.caption(t("calibration.evaluations", count=result.evaluations, message=result.message))
    if result.at_limit:
        st.warning(t("calibration.at_limit", names=", ".join(result.at_limit)))
    st.subheader(t("calibration.quality_title"))
    before = pd.DataFrame(quality_table_rows(result.before)).set_index("channel")
    after = pd.DataFrame(quality_table_rows(result.after)).set_index("channel")
    st.dataframe(pd.DataFrame({
        t("table.unit"): before["unit"],
        t("calibration.rmse_before"): before["rmse"], t("calibration.rmse_after"): after["rmse"],
        t("calibration.r2_before"): before["r_squared"],
        t("calibration.r2_after"): after["r_squared"]}), width="stretch")
    st.caption(t("calibration.quality_help"))
    profile = state.working_profile()
    if recording.synthetic:
        st.info(t("calibration.synthetic_note"))
    if st.button(t("calibration.accept", profile=profile.name), type="primary"):
        accept(profile, result, recording.synthetic)
        state.set_working_profile(profile)
        st.success(t("calibration.accepted"))


def render() -> None:
    """Draw the page."""
    st.title(t("calibration.title"))
    st.write(t("calibration.intro"))
    recording = _pick_recording()
    if recording is None:
        return
    numbers = [d.name for d in REGISTRY if d.kind is Kind.NUMBER]
    fit_params = st.multiselect(t("calibration.params"), numbers,
                                default=list(SUGGESTED_PARAMS[:2]),
                                format_func=batch_common.param_title,
                                help=t("calibration.params_help"))
    channels = [name for name in recording.data if recording.coverage(name) > 0.0]
    targets = st.multiselect(
        t("calibration.targets"), channels,
        default=[name for name in SUGGESTED_TARGETS if name in channels],
        format_func=lambda name: LOG_CHANNELS[name].title)
    budget = st.slider(t("calibration.budget"), 6, 120, 24, help=t("calibration.budget_help"))
    if st.button(t("calibration.run"), type="primary", disabled=not (fit_params and targets)):
        bar = st.progress(0.0)
        try:
            st.session_state[_RESULT] = calibrate(
                state.working_profile().params, recording, fit_params, targets, budget,
                progress=lambda count, _: bar.progress(min(1.0, count / budget)))
        except (ValueError, ParamError) as exc:
            st.error(str(exc))
        bar.empty()
    result: CalibrationResult | None = st.session_state.get(_RESULT)
    if result is not None:
        _show(result, recording)
