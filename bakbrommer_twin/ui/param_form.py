"""Input widgets generated from the parameter registry.

This is why a new parameter needs no UI work: :func:`render_category` walks
the registry and draws the right widget for each parameter kind.

Widgets store their changes through ``on_change`` callbacks. Streamlit runs
callbacks *before* it redraws the page, so everything drawn afterwards (change
counter, calculated values) already sees the new value.
"""

from __future__ import annotations

from typing import cast

import streamlit as st

from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.types import Kind, ParamDef, ParamError, ParamValue, Status
from bakbrommer_twin.ui import state
from bakbrommer_twin.ui.i18n import param_description, param_label, t

STATUSES = list(Status)
NEEDS_MEASURING = (Status.DEFAULT, Status.ESTIMATED)
_ERRORS = "param_errors"


def _key(name: str, part: str) -> str:
    return f"param::{state.widget_generation()}::{name}::{part}"


def _title(d: ParamDef) -> str:
    label = param_label(d)
    return f"{label} [{d.unit}]" if d.unit else label


def _parse_curve(text: str) -> list[float]:
    return [float(item) for item in text.replace(";", ",").split(",") if item.strip()]


def _on_value_change(name: str) -> None:
    """Callback: copy the widget value into the working profile (validated)."""
    params = state.working_profile().params
    errors: dict[str, str] = st.session_state.setdefault(_ERRORS, {})
    entered: ParamValue = st.session_state[_key(name, "value")]
    try:
        if REGISTRY.get(name).kind is Kind.CURVE:
            entered = _parse_curve(cast(str, entered))
        params.set_display(name, entered)
        errors.pop(name, None)
    except (ParamError, ValueError) as exc:
        errors[name] = str(exc)


def _on_status_change(name: str) -> None:
    """Callback: copy the chosen status into the working profile."""
    state.working_profile().params.set_status(name, st.session_state[_key(name, "status")])


def _value_widget(d: ParamDef, params: ParamSet) -> None:
    """Draw the widget for one parameter (shows the value in its friendly unit)."""
    current = params.display(d.name)
    key = _key(d.name, "value")
    help_text = f"{param_description(d)}  \n`{d.name}`"
    args = (d.name,)
    if d.kind is Kind.FLAG:
        st.checkbox(_title(d), value=cast(bool, current), help=help_text, key=key,
                    on_change=_on_value_change, args=args)
    elif d.kind is Kind.CHOICE:
        st.selectbox(_title(d), d.choices, index=d.choices.index(cast(str, current)),
                     help=help_text, key=key, on_change=_on_value_change, args=args)
    elif d.kind is Kind.CURVE:
        text = ", ".join(f"{v:g}" for v in cast(list[float], current))
        st.text_input(_title(d), value=text, key=key, on_change=_on_value_change, args=args,
                      help=f"{help_text}  \n{t('params.curve_help')}")
    elif d.kind is Kind.INTEGER:
        st.number_input(_title(d), value=cast(int, current), step=1, help=help_text, key=key,
                        on_change=_on_value_change, args=args)
    else:
        st.number_input(_title(d), value=float(cast(float, current)), format="%.6g",
                        help=help_text, key=key, on_change=_on_value_change, args=args)
    error = st.session_state.get(_ERRORS, {}).get(d.name)
    if error:
        st.error(t("params.invalid_value", error=error))


def render_param(d: ParamDef, params: ParamSet) -> None:
    """Draw one parameter row: value widget and status picker."""
    value_col, status_col = st.columns([3, 1.4])
    with value_col:
        _value_widget(d, params)
    with status_col:
        st.selectbox(
            t("params.status"), STATUSES, index=STATUSES.index(params.status(d.name)),
            format_func=lambda s: t(f"status.{s.value}"), key=_key(d.name, "status"),
            on_change=_on_status_change, args=(d.name,),
        )


def render_category(category: str, params: ParamSet) -> None:
    """Draw all parameters of one category, grouped by the second name part."""
    definitions = REGISTRY.in_category(category)
    todo = sum(1 for d in definitions if params.status(d.name) in NEEDS_MEASURING)
    st.caption(t("params.needs_measuring", count=todo, total=len(definitions)))
    groups: dict[str, list[ParamDef]] = {}
    for d in definitions:
        groups.setdefault(d.group, []).append(d)
    for group, members in groups.items():
        title = group.replace("_", " ").capitalize() if group else t("params.general_group")
        with st.expander(f"{title} ({len(members)})", expanded=len(groups) <= 2):
            for d in members:
                render_param(d, params)


def render_search(query: str, params: ParamSet) -> None:
    """Draw every parameter whose name, label or description contains ``query``."""
    needle = query.lower()
    for d in REGISTRY:
        haystack = f"{d.name} {param_label(d)} {param_description(d)}".lower()
        if needle in haystack:
            render_param(d, params)
