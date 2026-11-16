"""Page: scenario library and editor (segments table, route preview, draw a route)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from bakbrommer_twin.i18n import t
from bakbrommer_twin.params.definitions.control import RIDE_MODES
from bakbrommer_twin.params.definitions.wheels import SURFACE_NAMES
from bakbrommer_twin.params.types import ParamError
from bakbrommer_twin.reports.scenario_figures import drawing_canvas, route_preview
from bakbrommer_twin.scenarios.driver import plan_speed
from bakbrommer_twin.scenarios.metrics import METRIC_TYPES
from bakbrommer_twin.scenarios.route import Route
from bakbrommer_twin.scenarios.scenario import Scenario
from bakbrommer_twin.ui import scenario_form, state

_NEW = "__new__"
_EDIT = "scenario_edit"  # session key: dict(key, fields, frames, version)
_DRAWN = "scenario_drawn_points"
_PICK_NEXT = "scenario_pick_next"  # scenario to select when the page is drawn next
_SEGMENT_TYPES = ["straight", "arc", "slalom", "lane_change", "waypoints"]


def _blank() -> Scenario:
    return Scenario.model_validate(
        {"name": t("scenarios.new_name"), "route": [{"type": "straight", "length_m": 100.0}]})


def _load(key: str, scenario: Scenario) -> None:
    version = st.session_state.get(_EDIT, {}).get("version", 0) + 1
    st.session_state[_EDIT] = {
        "key": key, "version": version, "frames": scenario_form.scenario_frames(scenario),
        "fields": {"name": scenario.name, "description": scenario.description,
                   "category": scenario.category, "profile": scenario.profile,
                   "initial": scenario.initial.model_dump(),
                   "end": scenario.end.model_dump()}}
    st.session_state[_DRAWN] = []


def _fields(edit: dict[str, Any]) -> None:
    fields, version = edit["fields"], edit["version"]
    name_col, category_col = st.columns([3, 1])
    fields["name"] = name_col.text_input(t("scenarios.name"), fields["name"], key=f"sn{version}")
    fields["category"] = category_col.text_input(t("scenarios.category"), fields["category"],
                                                 key=f"sc{version}")
    fields["description"] = st.text_area(t("scenarios.description"), fields["description"],
                                         height=70, key=f"sd{version}")
    initial, end = fields["initial"], fields["end"]
    speed, mode, engine, profile = st.columns(4)
    initial["speed_kmh"] = speed.number_input(t("scenarios.initial_speed"), 0.0, 150.0,
                                              float(initial["speed_kmh"]), key=f"si{version}")
    initial["ride_mode"] = mode.selectbox(t("scenarios.initial_mode"), RIDE_MODES,
                                          RIDE_MODES.index(initial["ride_mode"]),
                                          key=f"sm{version}")
    initial["engine_running"] = engine.checkbox(t("scenarios.engine_running"),
                                                initial["engine_running"], key=f"se{version}")
    profiles = [None, *state.profile_store().list_keys()]
    fields["profile"] = profile.selectbox(
        t("scenarios.suggested_profile"), profiles,
        profiles.index(fields["profile"]) if fields["profile"] in profiles else 0,
        format_func=lambda p: p or "—", key=f"sp{version}")
    limit, at_speed, stopped, lift = st.columns(4)
    end["time_limit_s"] = limit.number_input(t("scenarios.time_limit"), 1.0, 7200.0,
                                             float(end["time_limit_s"]), key=f"st{version}")
    reach = at_speed.number_input(t("scenarios.end_speed"), 0.0, 200.0,
                                  float(end["at_speed_kmh"] or 0.0), key=f"sa{version}",
                                  help=t("scenarios.zero_is_off"))
    end["at_speed_kmh"] = reach or None
    end["when_stopped"] = stopped.checkbox(t("scenarios.end_stopped"), end["when_stopped"],
                                           key=f"sw{version}")
    end["on_wheel_lift"] = lift.checkbox(t("scenarios.end_lift"), end["on_wheel_lift"],
                                         key=f"sl{version}")


def _tables(edit: dict[str, Any]) -> dict[str, pd.DataFrame]:
    frames, version = edit["frames"], edit["version"]
    surfaces = ["", *SURFACE_NAMES]
    st.subheader(t("scenarios.segments"))
    st.caption(t("scenarios.segments_help"))
    edited = {"segments": st.data_editor(
        frames["segments"], num_rows="dynamic", key=f"seg{version}", width="stretch",
        column_config={
            "type": st.column_config.SelectboxColumn(options=_SEGMENT_TYPES, required=True),
            "surface": st.column_config.SelectboxColumn(options=surfaces),
            "surface_left": st.column_config.SelectboxColumn(options=surfaces),
            "surface_right": st.column_config.SelectboxColumn(options=surfaces),
            "points": st.column_config.TextColumn(help=t("scenarios.points_help")),
        })}
    with st.expander(t("scenarios.events")):
        st.caption(t("scenarios.events_help"))
        edited["events"] = st.data_editor(
            frames["events"], num_rows="dynamic", key=f"evt{version}", width="stretch",
            column_config={"set_mode": st.column_config.SelectboxColumn(
                options=list(RIDE_MODES), required=True)})
    with st.expander(t("scenarios.metrics")):
        st.caption(t("scenarios.metrics_help"))
        edited["metrics"] = st.data_editor(
            frames["metrics"], num_rows="dynamic", key=f"met{version}", width="stretch",
            column_config={"type": st.column_config.SelectboxColumn(
                options=list(METRIC_TYPES), required=True)})
    with st.expander(t("scenarios.overrides")):
        st.caption(t("scenarios.overrides_help"))
        edited["overrides"] = st.data_editor(frames["overrides"], num_rows="dynamic",
                                             key=f"ovr{version}", width="stretch")
    return edited


def _draw_tool(edit: dict[str, Any]) -> None:
    """Click grid points to lay out a route; turn it into one 'waypoints' segment."""
    st.caption(t("scenarios.draw_help"))
    points: list[tuple[float, float]] = st.session_state.setdefault(_DRAWN, [])
    size, spacing, undo, clear = st.columns(4)
    length = size.number_input(t("scenarios.draw_size"), 20.0, 2000.0, 100.0, 20.0)
    step = spacing.number_input(t("scenarios.draw_spacing"), 1.0, 50.0, 5.0, 1.0)
    if undo.button(t("scenarios.draw_undo"), disabled=not points, width="stretch"):
        points.pop()
    if clear.button(t("scenarios.draw_clear"), disabled=not points, width="stretch"):
        points.clear()
    event = st.plotly_chart(drawing_canvas(points, length, length / 2, step), width="stretch",
                            on_select="rerun", selection_mode="points",
                            key=f"draw{edit['version']}_{len(points)}")
    picked = event["selection"]["points"]
    if picked:
        point = (float(picked[0]["x"]), float(picked[0]["y"]))
        if point != (0.0, 0.0) and (not points or points[-1] != point):
            points.append(point)
            st.rerun()
    if st.button(t("scenarios.draw_use"), disabled=len(points) < 2, type="primary"):
        frames = edit["frames"]
        row = {"type": "waypoints", "points": "; ".join(f"{x:g}, {y:g}" for x, y in points),
               "speed_kmh": 30.0}
        frames["segments"] = pd.concat(
            [frames["segments"].iloc[0:0], pd.DataFrame([row])], ignore_index=True
        ).astype(frames["segments"].dtypes.to_dict())
        edit["version"] += 1
        st.session_state[_DRAWN] = []
        st.rerun()


def _save_bar(edit: dict[str, Any], scenario: Scenario | None) -> None:
    store = state.scenario_store()
    key_col, save_col, delete_col = st.columns([2, 1, 1])
    default_key = "" if edit["key"] == _NEW else edit["key"]
    key = key_col.text_input(t("scenarios.file_name"), default_key, key=f"sk{edit['version']}")
    if save_col.button(t("scenarios.save"), type="primary", width="stretch",
                       disabled=scenario is None or not key):
        try:
            store.save(key, scenario)  # type: ignore[arg-type]
            edit["key"] = key
            st.session_state[_PICK_NEXT] = key  # select it in the picker on the next run
            st.toast(t("scenarios.saved"))
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    with delete_col.popover(t("scenarios.delete"), width="stretch",
                            disabled=edit["key"] == _NEW):
        if st.button(t("scenarios.delete_confirm")):
            store.delete(edit["key"])
            del st.session_state[_EDIT]
            st.rerun()


def render() -> None:
    """Draw the page."""
    st.title(t("scenarios.title"))
    st.write(t("scenarios.intro"))
    store = state.scenario_store()
    keys = store.list_keys()
    library = {key: store.load(key) for key in keys}
    if _PICK_NEXT in st.session_state:
        st.session_state["scenario_pick"] = st.session_state.pop(_PICK_NEXT)
    pick = st.selectbox(
        t("scenarios.pick"), [*keys, _NEW], key="scenario_pick",
        format_func=lambda k: t("scenarios.new") if k == _NEW else (
            f"[{library[k].category}] {library[k].name}"))
    if _EDIT not in st.session_state or st.session_state[_EDIT]["key"] != pick:
        _load(pick, _blank() if pick == _NEW else library[pick])
    edit = st.session_state[_EDIT]
    _fields(edit)
    edited = _tables(edit)
    with st.expander(t("scenarios.draw_title")):
        _draw_tool(edit)
    scenario: Scenario | None = None
    try:
        scenario = scenario_form.build_scenario(edit["fields"], edited)
        params = state.working_profile().params.with_display_overrides(scenario.param_overrides)
        route = Route(scenario.route, params.num("sim.route_sample_spacing"),
                      params.choice("environment.default_surface"))
        plan = plan_speed(route, params.num("driver.max_lateral_accel"),
                          params.num("driver.max_deceleration"), [i for i, _ in route.stops])
        st.caption(t("scenarios.route_length", length=route.length))
        st.plotly_chart(route_preview(route, plan), width="stretch")
    except (ValueError, ParamError) as exc:
        scenario = None
        st.error(t("scenarios.invalid", error=exc))
    _save_bar(edit, scenario)
