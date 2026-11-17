"""Page: edit, save, compare and restore vehicle profiles."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from bakbrommer_twin.i18n import t
from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.derived import compute_derived
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.profile import Profile, ProfileStore, compare
from bakbrommer_twin.params.types import ParamError, ParamValue
from bakbrommer_twin.reports.curve_figures import CURVES
from bakbrommer_twin.ui import param_form, state

# curve key -> translation key of its title
CURVE_TITLES = {"tyres": "curves.tyres", "motor": "curves.motor", "engine": "curves.engine",
                "battery": "curves.battery"}


def _show(value: ParamValue) -> str:
    if isinstance(value, list):
        return ", ".join(f"{v:g}" for v in value)
    if isinstance(value, bool | str):
        return str(value)
    return f"{value:g}"


def _diff_table(a: ParamSet, b: ParamSet, name_a: str, name_b: str) -> None:
    rows = compare(a, b)
    if not rows:
        st.info(t("params.compare_none"))
        return
    st.caption(t("params.compare_count", count=len(rows)))
    st.dataframe(
        pd.DataFrame({
            t("params.col_parameter"): [f"{r.label} ({r.name})" for r in rows],
            t("params.col_unit"): [r.unit for r in rows],
            name_a: [f"{_show(r.value_a)}  [{r.status_a.value}]" for r in rows],
            name_b: [f"{_show(r.value_b)}  [{r.status_b.value}]" for r in rows],
        }),
        hide_index=True, width="stretch",
    )


def _saved_params(store: ProfileStore, profile: Profile) -> ParamSet:
    return store.load(profile.key).params if store.exists(profile.key) else ParamSet(REGISTRY)


def _profile_bar(store: ProfileStore, profile: Profile) -> None:
    """Profile picker, metadata and the save / copy / delete buttons."""
    keys = store.list_keys()
    index = keys.index(profile.key) if profile.key in keys else 0
    chosen = st.selectbox(t("params.profile"), keys, index=index)
    if chosen != profile.key:
        state.set_working_profile(store.load(chosen))
        st.rerun()
    name_col, base_col = st.columns([2, 1])
    profile.name = name_col.text_input(t("params.profile_name"), profile.name)
    base_col.text_input(t("params.based_on"), profile.base or t("params.no_base"), disabled=True)
    profile.description = st.text_input(t("params.profile_description"), profile.description)

    changes = len(_saved_params(store, profile).differences(profile.params))
    st.caption(t("params.unsaved", count=changes) if changes else t("params.no_changes"))
    save_col, revert_col, copy_col, delete_col = st.columns(4)
    if save_col.button(t("params.save"), type="primary", width="stretch"):
        store.save(profile)
        st.toast(t("params.saved"))
        st.rerun()
    if revert_col.button(t("params.revert"), disabled=changes == 0, width="stretch"):
        state.set_working_profile(store.load(profile.key))
        st.rerun()
    with copy_col.popover(t("params.save_as"), width="stretch"):
        new_key = st.text_input(t("params.new_key"))
        new_name = st.text_input(t("params.new_name"))
        if st.button(t("params.create"), disabled=not (new_key and new_name)):
            try:
                duplicate = Profile(new_key, new_name, profile.params.copy(),
                                    profile.description, profile.base, profile.validated,
                                    dict(profile.notes))
                if store.exists(new_key):
                    raise ParamError(f"'{new_key}' already exists")
                store.save(duplicate)
                state.set_working_profile(duplicate)
                st.rerun()
            except ParamError as exc:
                st.error(str(exc))
    with delete_col.popover(t("params.delete"), width="stretch"):
        if st.button(t("params.delete_confirm"), disabled=len(keys) < 2):
            try:
                store.delete(profile.key)
                state.set_working_profile(store.load(store.list_keys()[0]))
                st.toast(t("params.deleted"))
                st.rerun()
            except ParamError as exc:
                st.error(str(exc))


def _edit_tab(profile: Profile) -> None:
    query = st.text_input(t("params.search"))
    if query:
        param_form.render_search(query, profile.params)
        return
    categories = REGISTRY.categories()
    category = st.pills(t("params.category"), list(categories), default=next(iter(categories)),
                        format_func=lambda key: categories[key])
    if category:
        param_form.render_category(category, profile.params)


def _derived_tab(profile: Profile) -> None:
    st.caption(t("params.derived_intro"))
    values = compute_derived(profile.params)
    for group in dict.fromkeys(v.group for v in values):
        st.subheader(group)
        members = [v for v in values if v.group == group]
        st.dataframe(
            pd.DataFrame({
                t("params.col_parameter"): [v.label for v in members],
                t("params.col_value"): [f"{v.display:.4g}" for v in members],
                t("params.col_unit"): [v.unit for v in members],
            }),
            hide_index=True, width="stretch",
        )


def _curves_tab(profile: Profile) -> None:
    st.caption(t("curves.intro"))
    chosen = st.pills(t("curves.pick"), list(CURVES), default=next(iter(CURVES)),
                      format_func=lambda key: t(CURVE_TITLES[key]))
    if chosen:
        try:
            st.plotly_chart(CURVES[chosen](profile.params), width="stretch")
        except ValueError as exc:  # e.g. curve lists of different length
            st.error(str(exc))


def _compare_tab(store: ProfileStore, profile: Profile) -> None:
    keys = store.list_keys()
    current = f"{profile.key} {t('params.current_working')}"
    options = [current, *keys]
    col_a, col_b = st.columns(2)
    pick_a = col_a.selectbox(t("params.compare_a"), options, index=0)
    pick_b = col_b.selectbox(t("params.compare_b"), options, index=min(1, len(options) - 1))
    params_a = profile.params if pick_a == current else store.load(pick_a).params
    params_b = profile.params if pick_b == current else store.load(pick_b).params
    _diff_table(params_a, params_b, pick_a, pick_b)


def _history_tab(store: ProfileStore, profile: Profile) -> None:
    st.caption(t("params.history_intro"))
    stamps = store.history(profile.key)
    if not stamps:
        st.info(t("params.history_none"))
        return
    stamp = st.selectbox(t("params.history_version"), stamps)
    version = store.load_version(profile.key, stamp)
    _diff_table(version.params, profile.params, stamp, t("params.current_working"))
    if st.button(t("params.history_restore")):
        version.key = profile.key
        state.set_working_profile(version)
        st.toast(t("params.history_restored"))
        st.rerun()


def render() -> None:
    """Draw the page."""
    st.title(t("params.title"))
    st.write(t("params.intro"))
    store = state.profile_store()
    profile = state.working_profile()
    _profile_bar(store, profile)
    edit, derived, curves, compare_tab, history = st.tabs([
        t("params.tab_edit"), t("params.tab_derived"), t("params.tab_curves"),
        t("params.tab_compare"), t("params.tab_history"),
    ])
    with edit:
        _edit_tab(profile)
    with derived:
        _derived_tab(profile)
    with curves:
        _curves_tab(profile)
    with compare_tab:
        _compare_tab(store, profile)
    with history:
        _history_tab(store, profile)
