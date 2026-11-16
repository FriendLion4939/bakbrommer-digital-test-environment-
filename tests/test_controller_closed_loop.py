"""Reference controller driving the simulated vehicle (closed loop)."""

import numpy as np
import pytest
from helpers import SHIPPED_DATA, library_run, scenario, straight

from bakbrommer_twin.params import REGISTRY, ParamSet
from bakbrommer_twin.params.definitions.control import RIDE_MODES
from bakbrommer_twin.params.profile import ProfileStore
from bakbrommer_twin.sim.result import RunResult
from bakbrommer_twin.sim.simulator import run_scenario

KMH = 1 / 3.6


def _sprint(params: ParamSet, mode: str = "normal", seconds: float = 12.0,
            **fields: object) -> RunResult:
    return run_scenario(params, scenario(
        [straight(800, throttle=1.0)], initial={"ride_mode": mode},
        end={"time_limit_s": seconds},
        metrics=[{"type": "time_to_speed", "speed_kmh": 30}], **fields))


def _direct(params: ParamSet) -> ParamSet:
    other = params.copy()
    other.set("control.controller_type", "direct")
    return other


# ---- battery limits -------------------------------------------------------------------------

def test_battery_current_stays_within_the_controller_limit(params: ParamSet) -> None:
    result = _sprint(params, "sport")
    limit = params.num("control.limits.battery_current")
    assert result["battery_current"].max() < 1.08 * limit  # small overshoot + aux load
    assert result.metric("bms_trips") == 0.0 and result.metric("overcurrent_events") == 0.0


def test_central_limiter_protects_a_big_battery_setup() -> None:
    # 150 A BMS and 70 A per motor controller: only the central limiter holds 140 A.
    params = ProfileStore(SHIPPED_DATA / "profiles", REGISTRY).load("bms_150a").params
    result = _sprint(params, "standalone_electric", seconds=8.0)
    assert 120.0 < result["battery_current"].max() < 1.08 * 140.0
    assert result.metric("bms_trips") == 0.0
    assert result["ctl_power_limit"].min() < 0.9  # it really had to intervene


def test_low_battery_reduces_power_instead_of_tripping(params: ParamSet) -> None:
    params.set_display("battery.initial_soc", 9.0)  # rests at about 61 V
    result = _sprint(params, "standalone_electric", seconds=20.0)
    assert result["battery_voltage"].min() > params.num("battery.min_voltage") - 0.3
    assert result["ctl_power_limit"].min() < 0.7
    assert result["speed"][-1] > 3.0  # still moving, just gently
    assert result.metric("bms_trips") == 0.0
    empty = params.copy()
    empty.set_display("battery.initial_soc", 3.0)  # rests below the 60 V minimum
    flat = _sprint(empty, "standalone_electric", seconds=5.0)
    assert flat["ctl_torque_left"].max() == 0.0  # the controller refuses to drive


# ---- traction control and vectoring ---------------------------------------------------------

def _split_friction(params: ParamSet) -> RunResult:
    params.set("surface.mud.roughness_height", 0.0)
    return run_scenario(params, scenario(
        [straight(200, throttle=1.0, surface="dry_asphalt", surface_left="mud")],
        initial={"ride_mode": "sport"}, end={"time_limit_s": 5.0}))


def test_traction_control_stops_wheel_spin_on_split_friction(params: ParamSet) -> None:
    params.set_display("motor.line_current_limit", 60.0)  # enough torque to spin a wheel
    params.set("battery.bms_trip_enabled", False)
    without = params.copy()
    without.set("control.traction.enabled", False)
    with_tc, without_tc = _split_friction(params), _split_friction(without)
    assert without_tc["slip_ratio_fl"].max() > 0.5
    assert with_tc["slip_ratio_fl"][100:].max() < 0.5 * without_tc["slip_ratio_fl"].max()
    assert with_tc["ctl_traction_left"].max() > 0.2
    # the gripping side is hardly touched (a brief cut right at the launch is fine)
    assert with_tc["ctl_traction_right"].mean() < 0.1 * with_tc["ctl_traction_left"].mean()
    assert with_tc["speed"][-1] > 0.9 * without_tc["speed"][-1]  # no real loss of drive


def test_vectoring_favours_the_outer_wheel_and_prevents_inner_wheel_spin(
        params: ParamSet) -> None:
    def circle(p: ParamSet) -> RunResult:
        p.set("driver.max_lateral_accel", 2.5)
        return run_scenario(p, scenario(
            [straight(8, speed_kmh=30), {"type": "arc", "radius_m": 12, "angle_deg": 360,
                                         "speed_kmh": 30}], initial={"speed_kmh": 15}))

    brain, plain = circle(params.copy()), circle(_direct(params))
    # while cornering under power the outer (right) wheel gets the larger share
    driving = (brain["ctl_torque_left"] + brain["ctl_torque_right"] > 10.0) & (
        brain["accel_y"] > 1.0)
    assert driving.sum() > 50
    ahead = brain["ctl_torque_right"][driving] > brain["ctl_torque_left"][driving]
    assert ahead.mean() > 0.95
    assert brain["ctl_vectoring_torque"][driving].mean() > 2.0
    spin = [e for e in brain.meta.events if e.kind == "wheel_spin"]
    assert not spin
    assert brain["slip_ratio_fl"].max() <= plain["slip_ratio_fl"].max()


def test_rollover_protection_cuts_torque_in_hard_cornering(params: ParamSet) -> None:
    params.set("driver.max_lateral_accel", 3.4)
    result = run_scenario(params, scenario(
        [straight(10, speed_kmh=40), {"type": "arc", "radius_m": 12, "angle_deg": 270,
                                      "speed_kmh": 40}], initial={"speed_kmh": 20}))
    assert result["ctl_stability_limit"].min() < 0.6
    assert result["ctl_stability_limit"][:50].min() == 1.0  # nothing on the straight
    assert result.metric("rolled_over") == 0.0


# ---- regen ----------------------------------------------------------------------------------

def test_regen_recovers_energy_downhill_without_overcharging() -> None:
    result = library_run("hill_descent_10")
    assert (result.metric("regen_energy") or 0.0) > 2.0 * 3600  # more than 2 Wh
    assert result["battery_current"].min() < -3.0
    assert not any(e.kind in ("battery_overcharge", "bms_trip") for e in result.meta.events)
    assert result["ctl_regen_torque"].max() > 3.0


def test_regen_shortens_gentle_braking_energy_loss(params: ParamSet) -> None:
    item = scenario([straight(120, speed_kmh=40), straight(60, speed_kmh=10)],
                    initial={"speed_kmh": 40})
    brain, plain = run_scenario(params, item), run_scenario(_direct(params), item)
    assert brain.meta.energy["regen_energy"] > 500.0
    assert plain.meta.energy["regen_energy"] == 0.0
    assert brain.meta.energy["brake_loss"] < plain.meta.energy["brake_loss"]


# ---- ride modes -----------------------------------------------------------------------------

def test_modes_rank_by_performance(params: ParamSet) -> None:
    times = {mode: _sprint(params.copy(), mode).metric("time_0_30") or 99.0
             for mode in ("eco", "normal", "sport")}
    assert times["sport"] <= times["normal"] < times["eco"]


def test_eco_launches_electrically_then_starts_the_engine(params: ParamSet) -> None:
    result = _sprint(params, "eco", seconds=14.0, )
    speed, running = result["speed"], result["engine_running"]
    start_speed = params.num("control.mode_eco.engine_start_speed")
    # the engine was running at the start; eco switches it off, then on again at speed
    off = np.nonzero(running < 0.5)[0]
    assert len(off) > 0, "engine never switched off"
    restart = off[-1] + 1
    assert restart < len(running), "engine never came back"
    assert speed[restart] > start_speed
    assert running[-1] == 1.0
    assert result["ctl_mode"][-1] == RIDE_MODES.index("eco")


def test_standalone_electric_keeps_the_engine_off_and_hybrid_brings_it_back() -> None:
    result = library_run("mode_switch_sprint")
    distance, running = result["distance"], result["engine_running"]
    assert running[distance < 115.0].max() == 0.0
    assert result["engine_speed"][distance < 115.0].max() == 0.0
    assert running[-1] == 1.0
    assert result["ctl_mode"][0] == RIDE_MODES.index("standalone_electric")
    assert result["ctl_mode"][-1] == RIDE_MODES.index("normal")
    assert result["speed"][-1] > result["speed"][np.searchsorted(distance, 115.0)]


def test_mode_change_does_not_jerk_the_torque(params: ParamSet) -> None:
    result = run_scenario(params, scenario(
        [straight(800, speed_kmh=25)], initial={"speed_kmh": 25, "ride_mode": "eco"},
        events=[{"at_time_s": 4.0, "set_mode": "sport"}], end={"time_limit_s": 8.0}))
    window = (result["time"] > 3.9) & (result["time"] < 5.5)
    steps = np.abs(np.diff(result["ctl_torque_left"][window]))
    assert steps.max() < 5.0  # Nm per 10 ms sample
    assert np.abs(np.diff(result["accel_x"][window])).max() < 1.5


def test_throttle_by_wire_lets_the_controller_set_the_petrol_throttle(params: ParamSet) -> None:
    params.set("engine.throttle_by_wire", True)
    gain = params.num("control.mode_eco.engine_throttle_gain")
    result = _sprint(params, "eco", seconds=14.0)
    late = result["engine_running"] > 0.5
    late[: len(late) // 2] = False
    assert result["engine_throttle"][late].max() == pytest.approx(gain, abs=0.02)
    cable = params.copy()
    cable.set("engine.throttle_by_wire", False)
    assert _sprint(cable, "eco", seconds=14.0)["engine_throttle"].max() == pytest.approx(
        1.0, abs=0.01)


# ---- robustness to sensor quality -----------------------------------------------------------

def test_realistic_sensors_change_little(params: ParamSet) -> None:
    noisy = _sprint(params.copy()).metric("time_0_30") or 0.0
    ideal_params = params.copy()
    ideal_params.set("sensors.ideal", True)
    ideal = _sprint(ideal_params).metric("time_0_30") or 0.0
    assert noisy == pytest.approx(ideal, rel=0.05)


def test_speed_estimate_tracks_the_true_speed() -> None:
    result = library_run("race_lap_rough")
    error = np.abs(result["ctl_speed_estimate"] - result["speed"])
    assert np.percentile(error, 95) < 1.5  # m/s, on bumps with wheels in the air
    calm = library_run("range_cycle")
    assert np.abs(calm["ctl_speed_estimate"] - calm["speed"]).max() < 0.6
