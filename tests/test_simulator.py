"""Simulation loop: end conditions, events, determinism, results on disk."""

from pathlib import Path

import numpy as np
import pytest
from helpers import SHIPPED_DATA, scenario, straight

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.scenarios.scenario import Scenario, ScenarioStore
from bakbrommer_twin.sim.result import RunResult, list_runs
from bakbrommer_twin.sim.simulator import Simulation, run_scenario


def test_ends_at_route_end(quiet: ParamSet) -> None:
    result = run_scenario(quiet, scenario([straight(30, speed_kmh=20)]))
    assert result.meta.end_reason == "route_end"
    assert result["distance"][-1] >= 30.0


def test_ends_at_time_limit_and_speed(quiet: ParamSet) -> None:
    result = run_scenario(quiet, scenario([straight(500, throttle=1.0)],
                                          end={"time_limit_s": 2.0}))
    assert result.meta.end_reason == "time_limit"
    assert result.meta.duration == pytest.approx(2.0)
    result = run_scenario(quiet, scenario([straight(500, throttle=1.0)],
                                          end={"at_speed_kmh": 20}))
    assert result.meta.end_reason == "speed_reached"
    assert result["speed"][-1] * 3.6 == pytest.approx(20.0, abs=0.5)


def test_recording_rate_and_channels(quiet: ParamSet) -> None:
    result = run_scenario(quiet, scenario([straight(500, throttle=1.0)],
                                          end={"time_limit_s": 1.0}))
    assert len(result["time"]) == 101  # 100 Hz plus the start sample
    assert np.allclose(np.diff(result["time"]), 0.01)
    names = {c.name for c in result.meta.channels}
    assert {"speed", "load_fl", "battery_current", "engine_speed", "sens_gyro_z"} <= names
    assert set(result.data) == names
    assert result.display("speed")[-1] == pytest.approx(result["speed"][-1] * 3.6)


def test_same_inputs_give_identical_results(params: ParamSet) -> None:
    item = scenario([straight(500, throttle=1.0)], end={"time_limit_s": 3.0})
    first, second = run_scenario(params, item), run_scenario(params, item)
    for name in first.data:
        assert np.array_equal(first[name], second[name]), name
    params.set("sim.random_seed", 2)  # a different seed changes the sensor noise only
    third = run_scenario(params, item)
    assert not np.array_equal(first["sens_accel_x"], third["sens_accel_x"])


def test_mode_events_fire_at_time_and_distance(quiet: ParamSet) -> None:
    result = run_scenario(quiet, scenario(
        [straight(500, throttle=1.0)], end={"time_limit_s": 6.0},
        events=[{"at_time_s": 1.0, "set_mode": "sport"},
                {"at_distance_m": 20.0, "set_mode": "eco"}]))
    mode, time, distance = result["mode_request"], result["time"], result["distance"]
    assert mode[0] == 0
    assert mode[np.searchsorted(time, 1.05)] == 2  # sport
    assert mode[np.searchsorted(distance, 20.5)] == 1  # eco
    assert mode[-1] == 1


def test_scenario_overrides_are_applied_without_touching_the_profile(quiet: ParamSet) -> None:
    item = scenario([straight(50)], param_overrides={"mass.cargo.mass": 60})
    simulation = Simulation(quiet, item)
    assert simulation.vehicle.props.mass == pytest.approx(287.0)
    assert quiet.num("mass.cargo.mass") == 0.0


def test_initial_speed_picks_a_sensible_gear(quiet: ParamSet) -> None:
    simulation = Simulation(quiet, scenario([straight(50)], initial={"speed_kmh": 50}))
    assert simulation.vehicle.driveline.gear >= 3
    assert simulation.vehicle.chassis.u == pytest.approx(50 / 3.6)


def test_save_and_load_round_trip(quiet: ParamSet, tmp_path: Path) -> None:
    result = run_scenario(quiet, scenario([straight(500, throttle=1.0)],
                                          end={"time_limit_s": 1.0}), profile_name="Test")
    folder = result.save(tmp_path)
    loaded = RunResult.load(folder)
    assert loaded.meta == result.meta
    assert all(np.array_equal(loaded[n], result[n]) for n in result.data)
    assert list_runs(tmp_path) == [folder]
    assert loaded.meta.validated is False
    frame = loaded.to_dataframe()
    assert "speed [km/h]" in frame.columns and len(frame) == len(result["time"])


def test_metric_lookup(quiet: ParamSet) -> None:
    result = run_scenario(quiet, scenario(
        [straight(500, throttle=1.0)], end={"at_speed_kmh": 30},
        metrics=[{"type": "time_to_speed", "speed_kmh": 20},
                 {"type": "time_to_speed", "speed_kmh": 90}]))
    assert 0.5 < (result.metric("time_0_20") or 0.0) < 6.0
    assert result.metric("time_0_90") is None  # never reached
    assert result.metric("max_speed") == pytest.approx(30 / 3.6, abs=0.2)
    with pytest.raises(KeyError):
        result.metric("nonsense")


def test_every_shipped_scenario_is_valid() -> None:
    store = ScenarioStore(SHIPPED_DATA / "scenarios")
    assert len(store.list_keys()) >= 8
    for key in store.list_keys():
        assert isinstance(store.load(key), Scenario)


def test_scenario_store_round_trip(tmp_path: Path) -> None:
    store = ScenarioStore(tmp_path)
    item = scenario([straight(40, speed_kmh=25, surface="gravel")], category="demo")
    store.save("my_test", item)
    assert store.list_keys() == ["my_test"]
    assert store.load("my_test") == item
    store.delete("my_test")
    assert store.list_keys() == []


@pytest.mark.parametrize("bad", [
    {"name": "x", "route": []},
    {"name": "x", "route": [{"type": "arc", "radius_m": 5}]},
    {"name": "x", "route": [{"type": "straight", "length_m": 5, "surface": "ice"}]},
    {"name": "x", "route": [{"type": "straight", "length_m": 5}],
     "events": [{"set_mode": "turbo", "at_time_s": 1}]},
    {"name": "x", "route": [{"type": "straight", "length_m": 5}], "typo": 1},
])
def test_invalid_scenarios_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Scenario.model_validate(bad)
