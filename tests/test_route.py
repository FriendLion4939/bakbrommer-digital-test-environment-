"""Route geometry."""

import math

import pytest

from bakbrommer_twin.scenarios.route import Route
from bakbrommer_twin.scenarios.scenario import Segment


def _route(*segments: dict[str, object], spacing: float = 0.25) -> Route:
    return Route([Segment.model_validate(s) for s in segments], spacing)


def test_straight() -> None:
    route = _route({"type": "straight", "length_m": 100, "speed_kmh": 36, "gradient_pct": 5})
    assert route.length == pytest.approx(100.0)
    assert len(route) == 401
    assert route.x[-1] == pytest.approx(100.0) and route.y[-1] == pytest.approx(0.0)
    assert all(abs(c) < 1e-9 for c in route.curvature)
    assert route.speed[0] == pytest.approx(10.0) and route.grade[0] == pytest.approx(0.05)


def test_samples_are_plain_floats() -> None:
    route = _route({"type": "straight", "length_m": 20, "speed_end_kmh": 50},
                   {"type": "arc", "radius_m": 10, "angle_deg": 90})
    for name in ("s", "x", "y", "heading", "curvature", "speed", "grade", "throttle", "brake"):
        assert {type(v) for v in getattr(route, name)} == {float}, name


def test_left_arc_quarter_circle() -> None:
    route = _route({"type": "arc", "radius_m": 20, "angle_deg": 90})
    assert route.length == pytest.approx(20 * math.pi / 2, rel=1e-4)
    assert route.x[-1] == pytest.approx(20.0, abs=0.01)
    assert route.y[-1] == pytest.approx(20.0, abs=0.01)
    assert route.heading[-1] == pytest.approx(math.pi / 2, abs=0.02)
    middle = route.curvature[len(route) // 2]
    assert middle == pytest.approx(1 / 20, rel=0.01)


def test_right_arc_turns_the_other_way_and_segments_join() -> None:
    route = _route({"type": "straight", "length_m": 10},
                   {"type": "arc", "radius_m": 10, "angle_deg": -90},
                   {"type": "straight", "length_m": 10})
    assert route.x[-1] == pytest.approx(20.0, abs=0.02)
    assert route.y[-1] == pytest.approx(-20.0, abs=0.02)
    assert route.curvature[len(route) // 2] == pytest.approx(-0.1, rel=0.01)
    assert route.segment[0] == 0 and route.segment[-1] == 2


def test_speed_ramp_and_overrides() -> None:
    route = _route({"type": "straight", "length_m": 100, "speed_kmh": 0, "speed_end_kmh": 72},
                   {"type": "straight", "length_m": 10, "brake": 1.0})
    assert route.speed[route.index_at(50.0)] == pytest.approx(10.0, abs=0.05)
    assert math.isnan(route.throttle[0]) and math.isnan(route.brake[0])
    assert route.brake[-1] == 1.0 and math.isnan(route.throttle[-1])


def test_split_surfaces() -> None:
    route = _route({"type": "straight", "length_m": 10, "surface": "dry_asphalt",
                    "surface_left": "wet_asphalt"})
    assert route.surface_left[0] == "wet_asphalt"
    assert route.surface_right[0] == route.surface_center[0] == "dry_asphalt"


def test_locate_and_project() -> None:
    route = _route({"type": "straight", "length_m": 50},
                   {"type": "arc", "radius_m": 15, "angle_deg": 180})
    index = route.locate(30.1, 0.4, 0)
    distance, offset = route.project(index, 30.1, 0.4)
    assert distance == pytest.approx(30.1, abs=1e-6) and offset == pytest.approx(0.4)
    # a point 1 m outside the arc (to the right of the direction of travel)
    index = route.locate(50.0 + 16.0, 15.0, index)
    distance, offset = route.project(index, 66.0, 15.0)
    assert distance == pytest.approx(50.0 + 15 * math.pi / 2, abs=0.05)
    assert offset == pytest.approx(-1.0, abs=0.02)
    assert route.locate(30.0, 0.0, route.index_at(45.0)) == route.index_at(30.0)  # backwards
