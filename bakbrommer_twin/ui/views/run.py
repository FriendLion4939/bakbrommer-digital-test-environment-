"""Page: pick a scenario, run it with the working profile, look at the result."""

from __future__ import annotations

import streamlit as st

from bakbrommer_twin import paths
from bakbrommer_twin.i18n import t
from bakbrommer_twin.sim.simulator import run_scenario
from bakbrommer_twin.ui import state
from bakbrommer_twin.ui.result_view import render_result


def render() -> None:
    """Draw the page."""
    st.title(t("run.title"))
    st.write(t("run.intro"))
    store = state.scenario_store()
    profile = state.working_profile()
    scenarios = {key: store.load(key) for key in store.list_keys()}
    keys = sorted(scenarios, key=lambda k: (scenarios[k].category, scenarios[k].name))
    left, right = st.columns([2, 1])
    chosen = left.selectbox(
        t("run.scenario"), keys,
        format_func=lambda k: f"[{scenarios[k].category}] {scenarios[k].name}")
    scenario = scenarios[chosen]
    right.text_input(t("run.profile"), profile.name, disabled=True, help=t("run.profile_help"))
    st.caption(scenario.description)
    if scenario.profile and scenario.profile != profile.key:
        st.info(t("run.suggested_profile", profile=scenario.profile))
    name = st.text_input(t("run.name"), f"{scenario.name} — {profile.name}")
    pressed = st.button(t("run.start"), type="primary")
    # Always present, so the page layout (and the open result tab) stays the same on every rerun.
    progress_slot = st.empty()
    if pressed:
        bar = progress_slot.progress(0.0, t("run.running"))
        try:
            result = run_scenario(profile.params, scenario, profile_name=profile.name,
                                  validated=profile.validated, name=name,
                                  progress=lambda share: bar.progress(share, t("run.running")))
        except ValueError as exc:
            bar.empty()
            st.error(t("run.failed", error=exc))
            return
        bar.empty()
        folder = result.save(paths.runs_dir())
        state.set_current_result(result)
        st.toast(t("run.saved", folder=folder.name))
    shown = state.current_result()
    if shown is not None:
        st.divider()
        render_result(shown, key="run")
