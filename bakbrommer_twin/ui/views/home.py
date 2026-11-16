"""Page: start page with a short guide and the state of things."""

from __future__ import annotations

import streamlit as st

from bakbrommer_twin.i18n import t
from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.types import Status
from bakbrommer_twin.ui import state


def render() -> None:
    """Draw the page."""
    st.title(t("app.title"))
    st.write(t("home.intro"))
    profile = state.working_profile()
    params = profile.params
    unmeasured = sum(1 for d in REGISTRY
                     if params.status(d.name) in (Status.DEFAULT, Status.ESTIMATED))
    a, b, c, d = st.columns(4)
    a.metric(t("home.profile"), profile.name)
    b.metric(t("home.scenarios"), len(state.scenario_store().list_keys()))
    c.metric(t("home.saved_runs"), len(state.saved_runs()))
    d.metric(t("home.to_measure"), f"{unmeasured} / {len(REGISTRY)}")
    if not profile.validated:
        st.warning(t("app.not_validated"))
    st.subheader(t("home.steps_title"))
    st.markdown(t("home.steps"))
    st.subheader(t("home.measure_title"))
    st.markdown(t("home.measure"))
