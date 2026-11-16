"""Road model (surfaces, bumps, wind) and safety monitor."""

import math

import numpy as np
import pytest
from helpers import SHIPPED_DATA, Rig, scenario, straight

from bakbrommer_twin.params import REGISTRY, ParamSet
from bakbrommer_twin.params.profile import ProfileStore
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.scenarios.route import Route
from bakbrommer_twin.scenarios.scenario import Segment
from bakbrommer_twin.sim.safety import SafetyMonitor, rollover_margin
from bakbrommer_twin.sim.simulator import Simulation, run_scenario


def _route(*segments: dict[str, object]) -> Route:
    return Route([Segment.model_validate(s) for s in segments], 0.25, "dry_asphalt")


# ---- route shapes used by the lateral scenarios ------------------------------------

def test_slalom_weaves_and_returns_to_the_centre_line() -> None:
    route = _route({"type": "slalom", "cone_spacing_m": 9, "cones": 6, "lateral_offset_m": 1.0})
    ys = np.array(route.y)
    assert route.x[-1] == pytest.approx(63.0, abs=0.01)
    assert ys.max() == pytest.approx(1.0, abs=0.05) and ys.min() == pytest.approx(-1.0, abs=0.05)
    assert abs(route.y[-1]) < 1e-6 and abs(route.heading[-1]) < 0.01
    assert abs(route.heading[0]) < 0.01  # starts straight
    signs = np.sign(ys[np.abs(ys) > 0.5])
    assert np.count_nonzero(np.diff(signs)) == 6  # seven half-waves between six cones


def test_lane_change_shifts_sideways_and_stays_parallel() -> None:
    route = _route({"type": "lane_change", "length_m": 18, "lateral_offset_m": 3.0},
                   {"type": "straight", "length_m": 5})
    assert route.y[-1] == pytest.approx(3.0, abs=1e-3)
    assert abs(route.heading[-1]) < 1e-3
    assert route.length > 23.0  # longer than the straight-line distance


def test_waypoints_pass_through_the_given_points() -> None:
    points = [(10.0, 0.0), (20.0, 5.0), (30.0, 5.0)]
    route = _route({"type": "waypoints", "points": points}, {"type": "straight", "length_m": 5})
    for px, py in points:
        nearest = min(math.hypot(x - px, y - py) for x, y in zip(route.x, route.y, strict=True))
        assert nearest < 0.15
    assert abs(route.heading[0]) < 0.02  # leaves the start straight ahead
    with pytest.raises(ValueError, match="repeat"):
        _route({"type": "waypoints", "points": [(5.0, 0.0), (5.0, 0.0)]})


# ---- surfaces and bumps ----------------------------------------------------------------

def _wheel_heights(params: ParamSet, surface: str, speed_kmh: float = 20.0,
                   seconds: float = 20.0) -> tuple[np.ndarray, np.ndarray]:
    simulation = Simulation(params, scenario(
        [straight(2000, speed_kmh=speed_kmh, surface=surface)],
        initial={"speed_kmh": speed_kmh}, end={"time_limit_s": seconds}))
    heights: list[tuple[float, float]] = []
    wheels = simulation.vehicle.wheels

    def spy(_: float) -> None:
        heights.append((wheels[0].ground, wheels[1].ground))

    simulation.run(progress=spy)
    array = np.array(heights)
    return array[:, 0], array[:, 1]


def test_smooth_asphalt_is_flat(quiet: ParamSet) -> None:
    left, right = _wheel_heights(quiet, "dry_asphalt", seconds=3.0)
    assert np.all(left == 0.0) and np.all(right == 0.0)


def test_bump_height_matches_the_surface_parameter(quiet: ParamSet) -> None:
    left, right = _wheel_heights(quiet, "gravel")
    target = quiet.num("surface.gravel.roughness_height")
    assert np.std(left[200:]) == pytest.approx(target, rel=0.25)
    assert np.std(right[200:]) == pytest.approx(target, rel=0.25)
    assert abs(np.corrcoef(left[200:], right[200:])[0, 1]) < 0.6  # the two tracks differ


def test_bumps_depend_on_the_seed_only(quiet: ParamSet) -> None:
    first, _ = _wheel_heights(quiet, "gravel", seconds=3.0)
    again, _ = _wheel_heights(quiet, "gravel", seconds=3.0)
    quiet.set("sim.random_seed", 99)
    other, _ = _wheel_heights(quiet, "gravel", seconds=3.0)
    assert np.array_equal(first, again)
    assert not np.array_equal(first, other)


def test_rough_ground_shakes_the_wheel_loads(quiet: ParamSet) -> None:
    def load_spread(surface: str) -> float:
        result = run_scenario(quiet, scenario(
            [straight(2000, speed_kmh=20, surface=surface)], initial={"speed_kmh": 20},
            end={"time_limit_s": 10}))
        return float(np.std(result["load_fl"][200:]))

    assert load_spread("cobblestones") > 20 * max(load_spread("dry_asphalt"), 0.5)


def test_surface_changes_along_the_route_and_wet_profile_default(quiet: ParamSet) -> None:
    result = run_scenario(quiet, scenario(
        [straight(20, speed_kmh=20, surface="dry_asphalt"),
         straight(20, speed_kmh=20, surface="grass")], initial={"speed_kmh": 20}))
    assert result["surface_r"][0] == 0 and result["surface_r"][-1] == 3
    # the front wheels reach the grass before the rear wheel does
    change_front = np.argmax(result["surface_fl"] == 3)
    change_rear = np.argmax(result["surface_r"] == 3)
    assert change_front < change_rear
    wet = ProfileStore(SHIPPED_DATA / "profiles", REGISTRY).load("wet_weather").params
    simulation = Simulation(wet, scenario([straight(20)]))
    assert set(simulation.route.surface_center) == {"wet_asphalt"}


def test_headwind_lowers_and_tailwind_raises_coasting_speed(quiet: ParamSet) -> None:
    def speed_after_coasting(direction_deg: float) -> float:
        params = quiet.copy()
        params.set_display("environment.wind_speed", 40.0)
        params.set_display("environment.wind_direction", direction_deg)
        result = run_scenario(params, scenario(
            [straight(2000, throttle=0.0)], initial={"speed_kmh": 40, "engine_running": False},
            end={"time_limit_s": 6}))
        return float(result["speed"][-1])

    assert speed_after_coasting(0.0) < speed_after_coasting(90.0) < speed_after_coasting(180.0)


def test_cross_wind_pushes_the_vehicle_off_its_line(quiet: ParamSet) -> None:
    quiet.set_display("environment.wind_speed", 60.0)
    quiet.set_display("environment.wind_direction", 90.0)  # from the left
    result = run_scenario(quiet, scenario([straight(150, speed_kmh=30)],
                                          initial={"speed_kmh": 30}))
    assert result["route_offset"].min() < -0.02  # pushed to the right
    assert result["steer"][-1] > 0.0  # the rider steers into the wind


# ---- safety monitor ------------------------------------------------------------------------

def test_rollover_margin_definition(params: ParamSet) -> None:
    wheels = Vehicle(params).wheels
    wheels[0].load, wheels[1].load = 500.0, 500.0
    assert rollover_margin(wheels) == 1.0
    wheels[0].load, wheels[1].load = 250.0, 750.0
    assert rollover_margin(wheels) == pytest.approx(0.5)
    wheels[0].load, wheels[1].load = 0.0, 900.0
    assert rollover_margin(wheels) == 0.0
    wheels[0].load, wheels[1].load = 0.0, 0.0
    assert rollover_margin(wheels) == 1.0  # both in the air (a bump), not a rollover sign


def test_events_need_their_minimum_duration(params: ParamSet) -> None:
    rig = Rig(params)
    monitor = SafetyMonitor(params, rig.vehicle)
    wheel = rig.vehicle.wheels[0]
    wheel.gap = 0.02
    monitor.update(1.00)
    wheel.gap = 0.0
    monitor.update(1.02)  # 20 ms hop: shorter than the 50 ms minimum
    assert monitor.events == []
    wheel.gap = 0.03
    monitor.update(2.00)
    wheel.gap = 0.05
    monitor.update(2.20)
    assert monitor.has_open_or_recorded("wheel_lift", 2.20)
    wheel.gap = 0.0
    monitor.update(2.30)
    (event,) = monitor.events
    assert (event.kind, event.subject, event.start, event.end) == ("wheel_lift", "fl", 2.0, 2.3)
    assert event.peak == pytest.approx(50.0) and event.unit == "mm"


def test_electrical_and_thermal_events(params: ParamSet) -> None:
    rig = Rig(params)
    vehicle = rig.vehicle
    monitor = SafetyMonitor(params, vehicle)
    vehicle.battery.current = 50.0
    vehicle.battery.voltage = 55.0
    vehicle.drive_left.temperature = 150.0
    monitor.update(1.0)
    vehicle.battery.current = 5.0
    vehicle.battery.voltage = 66.0
    vehicle.drive_left.temperature = 50.0
    monitor.update(2.0)
    monitor.finish(3.0)
    kinds = {(e.kind, e.subject) for e in monitor.events}
    assert kinds == {("battery_overcurrent", ""), ("battery_undervoltage", ""),
                     ("motor_derating", "left"), ("motor_overheat", "left")}
    low = next(e for e in monitor.events if e.kind == "battery_undervoltage")
    assert low.peak == pytest.approx(55.0)  # reported as the lowest voltage, not negated


def test_open_events_are_closed_at_the_end_and_rollover_is_flagged(params: ParamSet) -> None:
    rig = Rig(params)
    monitor = SafetyMonitor(params, rig.vehicle)
    rig.vehicle.chassis.roll = math.radians(70.0)
    monitor.update(1.0)
    assert monitor.rolled_over
    monitor.finish(1.5)
    kinds = [e.kind for e in monitor.events]
    assert "rollover" in kinds and "past_tip_over_point" in kinds
