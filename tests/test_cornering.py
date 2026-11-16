"""Cornering: steady-state turning, load transfer, wheel lift and rollover."""

import math

import numpy as np
import pytest
from helpers import scenario, straight

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.params.derived import derived_dict
from bakbrommer_twin.physics import mass
from bakbrommer_twin.sim.result import RunResult
from bakbrommer_twin.sim.simulator import run_scenario

G = mass.GRAVITY


def _circle(params: ParamSet, speed_kmh: float, radius: float = 15.0, angle: float = 270.0,
            **fields: object) -> RunResult:
    """Drive part of a circle at constant target speed (the rider may not slow down)."""
    params.set("driver.max_lateral_accel", 12.0)
    return run_scenario(params, scenario(
        [straight(8, speed_kmh=speed_kmh),
         {"type": "arc", "radius_m": radius, "angle_deg": angle, "speed_kmh": speed_kmh}],
        initial={"speed_kmh": speed_kmh}, **fields))


def _late(result: RunResult, name: str) -> float:
    """Mean of a channel over the last third of the run (steady state)."""
    values = result[name]
    return float(np.mean(values[2 * len(values) // 3:]))


def test_steady_turn_kinematics(quiet: ParamSet) -> None:
    result = _circle(quiet, 15.0)
    speed, radius = _late(result, "speed"), 15.0
    assert _late(result, "yaw_rate") == pytest.approx(speed / radius, rel=0.03)
    assert _late(result, "accel_y") == pytest.approx(speed**2 / radius, rel=0.06)
    assert abs(_late(result, "route_offset")) < 0.3


def test_right_turn_mirrors_left_turn(quiet: ParamSet) -> None:
    left = _circle(quiet.copy(), 15.0, angle=270.0)
    right = _circle(quiet.copy(), 15.0, angle=-270.0)
    assert _late(right, "yaw_rate") == pytest.approx(-_late(left, "yaw_rate"), rel=1e-3)
    assert _late(right, "load_fl") == pytest.approx(_late(left, "load_fr"), rel=1e-3)
    assert _late(right, "roll") == pytest.approx(-_late(left, "roll"), rel=1e-3)


def test_lateral_load_transfer_goes_through_the_front_axle(quiet: ParamSet) -> None:
    result = _circle(quiet, 15.0)
    props = mass.mass_properties(quiet)
    lateral = _late(result, "speed") ** 2 / 15.0
    # A single rear wheel cannot resist roll: the whole moment m·a_y·h is carried by
    # the front track:  F_right − F_left = m·a_y·h / (t/2)
    expected = props.mass * lateral * props.cog_height / (quiet.num("geometry.front_track") / 2)
    measured = _late(result, "load_fr") - _late(result, "load_fl")
    assert measured == pytest.approx(expected, rel=0.08)
    total = sum(_late(result, f"load_{w}") for w in ("fl", "fr", "r"))
    assert total == pytest.approx(props.mass * G, rel=0.01)
    assert _late(result, "roll") > 0.0  # left turn: left side rises


def _lift_speed(params: ParamSet, **fields: object) -> tuple[float, float]:
    params.set("driver.max_lateral_accel", 12.0)
    result = run_scenario(params, scenario(
        [straight(8, speed_kmh=10),
         {"type": "arc", "radius_m": 12, "angle_deg": 1800, "speed_kmh": 10,
          "speed_end_kmh": 60}],
        initial={"speed_kmh": 10}, end={"time_limit_s": 120, "on_wheel_lift": True},
        metrics=[{"type": "wheel_lift_speed"}, {"type": "wheel_lift_lateral_accel"}], **fields))
    assert result.meta.end_reason == "wheel_lift"
    return (result.metric("wheel_lift_speed") or 0.0,
            result.metric("wheel_lift_lateral_accel") or 0.0)


def test_wheel_lift_agrees_with_rigid_vehicle_estimate(quiet: ParamSet) -> None:
    estimate = derived_dict(quiet)["lift_accel_left_turn"]
    speed, lateral = _lift_speed(quiet)
    assert lateral == pytest.approx(estimate, rel=0.10)
    assert speed == pytest.approx(math.sqrt(estimate * 12.0), rel=0.08)


def test_higher_cargo_lifts_a_wheel_sooner(quiet: ParamSet) -> None:
    low, high = quiet.copy(), quiet.copy()
    for params, height in ((low, 0.5), (high, 1.1)):
        params.set("mass.cargo.mass", 80.0)
        params.set("mass.cargo.height", height)
    assert _lift_speed(high)[0] < 0.92 * _lift_speed(low)[0]


def test_wider_track_lifts_later(quiet: ParamSet) -> None:
    wide = quiet.copy()
    wide.set("geometry.front_track", 1.05)
    assert _lift_speed(wide)[0] > 1.05 * _lift_speed(quiet.copy())[0]


def test_ackermann_steering_corners_too(quiet: ParamSet) -> None:
    quiet.set("steering.type", "ackermann")
    result = _circle(quiet, 15.0)
    assert _late(result, "yaw_rate") == pytest.approx(_late(result, "speed") / 15.0, rel=0.03)
    assert _late(result, "steer_fl") > _late(result, "steer_fr") > 0.0


def test_rider_who_does_not_react_rolls_over(quiet: ParamSet) -> None:
    quiet.set("driver.lift_reaction_gain", 0.0)
    result = _circle(quiet, 30.0, radius=12.0, end={"time_limit_s": 30})
    assert result.meta.end_reason == "rollover"
    kinds = [event.kind for event in result.meta.events]
    assert kinds.index("wheel_lift") < kinds.index("past_tip_over_point") < kinds.index(
        "rollover")
    assert result.metric("rolled_over") == 1.0
    assert result.metric("min_rollover_margin") == 0.0


def test_reacting_rider_keeps_it_upright_with_a_wheel_in_the_air(quiet: ParamSet) -> None:
    result = _circle(quiet, 30.0, radius=12.0, end={"time_limit_s": 30})
    assert result.meta.end_reason == "route_end"
    lifts = [e for e in result.meta.events if e.kind == "wheel_lift" and e.subject == "fl"]
    assert lifts, "the inner wheel must lift at this speed"
    assert (result.metric("max_roll") or 9.0) < math.radians(15.0)
    assert (result.metric("max_wheel_lift") or 0.0) > 0.005


def test_split_friction_spins_only_the_slippery_side(quiet: ParamSet) -> None:
    quiet.set("surface.mud.roughness_height", 0.0)
    result = run_scenario(quiet, scenario(
        [straight(120, throttle=1.0, surface="dry_asphalt", surface_left="mud")],
        end={"time_limit_s": 4.0}))
    spinning = {e.subject for e in result.meta.events if e.kind == "wheel_spin"}
    assert spinning == {"fl"}
    assert result["slip_ratio_fl"].max() > 5 * result["slip_ratio_fr"].max()
    assert result["fx_fr"].max() > 1.2 * result["fx_fl"].max()
    assert result["surface_fl"][5] != result["surface_fr"][5]


def test_wet_road_slides_at_a_speed_that_dry_road_holds(quiet: ParamSet) -> None:
    # very low CoG so that grip, not wheel lift, is the limit
    for component in mass.COMPONENTS:
        quiet.set(f"mass.{component}.height", 0.12)
    quiet.set_display("safety.slip_angle_limit", 9.0)  # just beyond the 8° peak-grip angle
    dry = _circle(quiet.copy(), 38.0, radius=15.0, angle=180.0)
    wet_params = quiet.copy()
    wet_params.set("environment.default_surface", "wet_asphalt")
    wet = _circle(wet_params, 38.0, radius=15.0, angle=180.0)
    assert abs(_late(dry, "route_offset")) < 0.5
    assert np.abs(wet["route_offset"]).max() > 2 * np.abs(dry["route_offset"]).max()
    assert any(e.kind == "side_slide" for e in wet.meta.events)
