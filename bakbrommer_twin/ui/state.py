"""Shared session state of the web interface.

Streamlit re-runs a page script on every interaction; anything that must
survive lives in ``st.session_state``. All access goes through the helpers
here so the key names are in one place.
"""

from __future__ import annotations

import streamlit as st

from bakbrommer_twin import paths
from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.profile import Profile, ProfileStore

_PROFILE = "working_profile"
_GENERATION = "widget_generation"
DEFAULT_PROFILE_KEY = "default"


def profile_store() -> ProfileStore:
    """The store for the profiles folder."""
    return ProfileStore(paths.profiles_dir(), REGISTRY)


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
