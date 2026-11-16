"""Physical plausibility of the cornering scenarios (Phase 3)."""

import math

import numpy as np
from helpers import library_run

from bakbrommer_twin.params import default_params
from bakbrommer_twin.params.derived import derived_dict


def test_circle_finds_the_wheel_lift_speed() -> None:
    result = library_run("steady_circle")
    assert result.meta.end_reason == "wheel_lift"
    estimate = derived_dict(default_params())["lift_accel_left_turn"]
    lift_speed = result.metric("wheel_lift_speed") or 0.0
    assert abs(lift_speed - math.sqrt(estimate * 12.0)) < 0.08 * lift_speed
    lifted = [e.subject for e in result.meta.events if e.kind == "wheel_lift"]
    assert lifted == ["fl"]  # left turn: the inner (left) wheel lifts
    assert (result.metric("max_route_offset") or 9.0) < 0.5


def test_slalom_swings_the_load_from_side_to_side() -> None:
    result = library_run("slalom")
    assert result.meta.end_reason == "route_end"
    difference = result["load_fl"] - result["load_fr"]
    assert difference.max() > 300.0 and difference.min() < -300.0
    assert np.count_nonzero(np.diff(np.sign(difference[np.abs(difference) > 150.0]))) >= 5
    assert (result.metric("max_route_offset") or 9.0) < 0.6
    assert result.metric("rolled_over") == 0.0


def test_roundabout_is_taken_cleanly_by_the_default_rider() -> None:
    result = library_run("roundabout")
    assert result.meta.end_reason == "route_end"
    assert result.metric("wheel_lift_events") == 0.0
    assert (result.metric("max_route_offset") or 9.0) < 0.5
    assert result["speed"].min() < 0.75 * result["speed"][0]  # slows down for the bends
    assert 0.0 < (result.metric("min_rollover_margin") or 0.0) < 0.6


def test_lane_change_with_cargo_stays_on_three_wheels() -> None:
    result = library_run("lane_change_full_cargo")
    assert result.meta.profile_name == "Full cargo"
    assert result.meta.end_reason == "route_end"
    assert result.metric("wheel_lift_events") == 0.0
    assert (result.metric("max_route_offset") or 9.0) < 0.4
    assert (result.metric("min_rollover_margin") or 0.0) > 0.2


def test_split_friction_spins_the_wheel_on_mud_but_stays_straight() -> None:
    result = library_run("split_friction_accel")
    assert result.meta.end_reason == "speed_reached"
    assert {e.subject for e in result.meta.events if e.kind == "wheel_spin"} == {"fl"}
    assert (result.metric("max_route_offset") or 9.0) < 0.3
