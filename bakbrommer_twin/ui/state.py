"""Shared session state of the web interface.

Streamlit re-runs a page script on every interaction; anything that must
survive lives in ``st.session_state``. All access goes through the helpers
here so the key names are in one place.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from bakbrommer_twin import paths
from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.profile import Profile, ProfileStore
from bakbrommer_twin.scenarios.scenario import ScenarioStore
from bakbrommer_twin.sim.result import RunResult, list_runs

_PROFILE = "working_profile"
_GENERATION = "widget_generation"
_RESULT = "current_result"
DEFAULT_PROFILE_KEY = "default"


def profile_store() -> ProfileStore:
    """The store for the profiles folder."""
    return ProfileStore(paths.profiles_dir(), REGISTRY)


def scenario_store() -> ScenarioStore:
    """The store for the scenarios folder."""
    return ScenarioStore(paths.scenarios_dir())


def working_profile() -> Profile:
    """The profile currently being edited/used (loaded on first use)."""
    if _PROFILE not in st.session_state:
        store = profile_store()
        keys = store.list_keys()
        key = DEFAULT_PROFILE_KEY if DEFAULT_PROFILE_KEY in keys else keys[0]
        st.session_state[_PROFILE] = store.load(key)
    profile: Profile = st.session_state[_PROFILE]
    return profile


def set_working_profile(profile: Profile) -> None:
    """Replace the working profile and reset all parameter widgets."""
    st.session_state[_PROFILE] = profile
    st.session_state[_GENERATION] = widget_generation() + 1


def widget_generation() -> int:
    """Counter that is part of widget keys; bumping it resets the widgets."""
    return int(st.session_state.get(_GENERATION, 0))


def current_result() -> RunResult | None:
    """The run most recently simulated or opened in this browser session."""
    result: RunResult | None = st.session_state.get(_RESULT)
    return result


def set_current_result(result: RunResult) -> None:
    """Remember a run as the one being looked at."""
    st.session_state[_RESULT] = result


def saved_runs() -> list[Path]:
    """Folders of all saved runs, newest first."""
    return list_runs(paths.runs_dir())


@st.cache_data(show_spinner=False, max_entries=24)
def _load_run(folder: str, modified: float) -> RunResult:
    return RunResult.load(Path(folder))


def load_run(folder: Path) -> RunResult:
    """Load a saved run (cached per browser session)."""
    return _load_run(str(folder), folder.stat().st_mtime)
