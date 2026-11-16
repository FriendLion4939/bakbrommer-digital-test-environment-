"""Driver model: speed planning, pedals, gear changes."""

import math

import pytest
from helpers import Rig, library_run, scenario, straight

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.scenarios.driver import RouteDriver, plan_speed
from bakbrommer_twin.scenarios.route import Route
from bakbrommer_twin.scenarios.scenario import Segment
from bakbrommer_twin.sim.simulator import run_scenario


def _route(*segments: dict[str, object]) -> Route:
    return Route([Segment.model_validate(s) for s in segments], 0.25)


def test_plan_slows_for_corners_and_brakes_in_time() -> None:
    route = _route({"type": "straight", "length_m": 100, "speed_kmh": 72},
                   {"type": "arc", "radius_m": 10, "angle_deg": 90, "speed_kmh": 72})
    plan = plan_speed(route, max_lateral_accel=2.5, max_deceleration=3.0)
    corner = math.sqrt(2.5 * 10)
    assert plan[route.index_at(110.0)] == pytest.approx(corner, rel=0.02)
    assert plan[0] == pytest.approx(20.0)
    # 5 m before the corner the plan allows v² = v_corner² + 2·a·d
    assert plan[route.index_at(95.0)] == pytest.approx(math.sqrt(corner**2 + 2 * 3.0 * 5.0),
                                                       rel=0.03)


def test_plan_ignores_fixed_pedal_sections() -> None:
    route = _route({"type": "straight", "length_m": 50, "speed_kmh": 50},
                   {"type": "straight", "length_m": 50, "speed_kmh": 0, "brake": 1.0})
    plan = plan_speed(route, 2.5, 3.0)
    assert plan[0] == pytest.approx(50 / 3.6)  # no early braking for the brake section
    assert plan[-1] == math.inf


def test_plan_stops_at_a_zero_speed_segment() -> None:
    route = _route({"type": "straight", "length_m": 50, "speed_kmh": 36},
                   {"type": "straight", "length_m": 5, "speed_kmh": 0})
    plan = plan_speed(route, 2.5, 3.0)
    assert plan[route.index_at(50.5)] == 0.0
    assert 0.0 < plan[route.index_at(49.0)] < 4.0


def test_driver_holds_target_speed(quiet: ParamSet) -> None:
    result = run_scenario(quiet, scenario([straight(400, speed_kmh=30)],
                                          end={"time_limit_s": 40}))
    late = result["speed"][result["time"] > 15.0]
    assert late.mean() * 3.6 == pytest.approx(30.0, abs=0.5)
    assert late.std() * 3.6 < 0.5


def test_driver_stops_at_planned_stop(quiet: ParamSet) -> None:
    result = run_scenario(quiet, scenario(
        [straight(80, speed_kmh=30), straight(10, speed_kmh=0)],
        initial={"speed_kmh": 30}, end={"time_limit_s": 40, "when_stopped": True}))
    assert result.meta.end_reason == "stopped"
    assert result["distance"][-1] == pytest.approx(80.0, abs=2.0)


def test_driver_shifts_up_through_the_gears() -> None:
    result = library_run("top_speed")
    gears = result["gear"]
    assert gears[0] == 1 and gears.max() >= 3
    assert (gears[1:] >= gears[:-1]).all()  # only upshifts during full acceleration


def test_gear_logic_shifts_down_when_slow(quiet: ParamSet) -> None:
    rig = Rig(quiet, speed=4.0, gear=3)
    route = _route({"type": "straight", "length_m": 100, "speed_kmh": 20})
    driver = RouteDriver(quiet, route)
    driver.update(0.01, rig.vehicle, rig.rider)
    assert rig.rider.gear == 2


def test_throttle_closed_while_shifting(quiet: ParamSet) -> None:
    rig = Rig(quiet, speed=4.0, gear=1)
    driver = RouteDriver(quiet, _route({"type": "straight", "length_m": 100, "throttle": 1.0}))
    rig.rider.gear = 2
    rig.run(0.01)  # the gearbox starts the change
    driver.update(0.01, rig.vehicle, rig.rider)
    assert rig.vehicle.driveline.shifting and rig.rider.throttle == 0.0
