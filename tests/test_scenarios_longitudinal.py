"""Physical plausibility of the straight-line scenarios (Phase 2)."""

import pytest
from helpers import SHIPPED_DATA, library_run

from bakbrommer_twin.params import default_params
from bakbrommer_twin.params.derived import derived_dict
from bakbrommer_twin.scenarios.scenario import ScenarioStore
from bakbrommer_twin.sim.simulator import run_scenario

KMH = 3.6


def test_acceleration_time_is_plausible_and_clean() -> None:
    result = library_run("accel_0_50")
    assert result.meta.end_reason == "speed_reached"
    assert 5.0 < (result.metric("time_0_50") or 0.0) < 12.0
    assert (result.metric("time_0_30") or 99.0) < (result.metric("time_0_50") or 0.0)
    assert result.meta.events == []  # default limits keep the battery below the BMS limit
    assert (result.metric("energy_balance_error") or 1.0) < 0.005


def test_full_cargo_accelerates_slower() -> None:
    empty = library_run("accel_0_50").metric("time_0_50") or 0.0
    loaded = library_run("accel_0_50", "full_cargo").metric("time_0_50") or 0.0
    assert loaded > 1.15 * empty


def test_top_speed_agrees_with_the_power_balance_estimate() -> None:
    # The estimate assumes engine and motors both at full power, so compare it with
    # the direct controller (Normal mode fades the electric assist out at speed).
    params = default_params()
    params.set("control.controller_type", "direct")
    params.set_display("control.direct.max_torque", 115.0)
    item = ScenarioStore(SHIPPED_DATA / "scenarios").load("top_speed")
    result = run_scenario(params, item)
    estimate = derived_dict(params)["top_speed_estimate"]
    assert result.metric("top_speed") == pytest.approx(estimate, rel=0.06)
    assert result.metric("steady_speed") == pytest.approx(result.metric("top_speed"), rel=0.01)
    assert (library_run("top_speed").metric("top_speed") or 0.0) < estimate


def test_steeper_hills_are_climbed_slower() -> None:
    speeds = [library_run(f"hill_climb_{g}").metric("steady_speed") or 0.0 for g in (5, 10, 15)]
    assert speeds[0] > speeds[1] > speeds[2] > 15 / KMH
    assert speeds[0] < (library_run("top_speed").metric("top_speed") or 0.0)


def test_descent_is_held_at_target_speed_with_the_brakes() -> None:
    result = library_run("hill_descent_10")
    assert result.metric("steady_speed") == pytest.approx(30 / KMH, abs=1.0 / KMH)
    assert (result.metric("max_speed") or 99.0) < 34 / KMH
    # gravity work is shared between brakes, engine braking, air and rolling resistance
    assert result.meta.energy["brake_loss"] > 0.2 * result.meta.energy["gravity_work"] > 0.0


def test_emergency_braking_dry_versus_wet() -> None:
    dry, wet = library_run("emergency_brake_dry"), library_run("emergency_brake_wet")
    assert dry.meta.end_reason == wet.meta.end_reason == "stopped"
    dry_distance = dry.metric("braking_distance") or 0.0
    wet_distance = wet.metric("braking_distance") or 0.0
    assert 8.0 < dry_distance < 16.0  # 50 km/h → 0 at 0.6–1.2 g
    assert wet_distance > 1.25 * dry_distance
    # deceleration can never beat friction × gravity (plus a little drag)
    assert (dry.metric("braking_deceleration") or 99.0) < 1.1 * 0.95 * 9.81


def test_full_lever_locks_the_front_wheels_and_this_is_reported() -> None:
    result = library_run("emergency_brake_dry")
    locked = {event.subject for event in result.meta.events if event.kind == "wheel_lock"}
    assert {"fl", "fr"} <= locked
    assert result.metric("wheel_lock_events") >= 2
