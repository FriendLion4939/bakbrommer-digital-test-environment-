"""Steering geometry: centre-pivot and Ackermann."""

import math

import pytest

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.physics.vehicle import Vehicle

HALF_TRACK = 0.425
WHEELBASE = 1.6


def _steered(params: ParamSet, handlebar_deg: float) -> Vehicle:
    vehicle = Vehicle(params)
    vehicle.steering.apply(math.radians(handlebar_deg), vehicle.wheels)
    return vehicle


def test_centre_pivot_turns_the_whole_axle(params: ParamSet) -> None:
    vehicle = _steered(params, 20.0)
    left, right, rear = vehicle.wheels
    angle = math.radians(20.0)
    assert left.steer == right.steer == pytest.approx(angle)
    assert rear.steer == 0.0
    # left turn: left wheel moves back, right wheel forward; the axle keeps its length
    assert left.x == pytest.approx(left.base_x - HALF_TRACK * math.sin(angle))
    assert right.x == pytest.approx(right.base_x + HALF_TRACK * math.sin(angle))
    assert math.hypot(left.x - right.x, left.y - right.y) == pytest.approx(2 * HALF_TRACK)
    assert left.y - right.y == pytest.approx(2 * HALF_TRACK * math.cos(angle))


def test_centre_pivot_with_pin_behind_the_axle(params: ParamSet) -> None:
    params.set("steering.pivot_offset", 0.3)
    vehicle = _steered(params, 15.0)
    left, right, _ = vehicle.wheels
    angle = math.radians(15.0)
    centre_x = 0.5 * (left.x + right.x)
    centre_y = 0.5 * (left.y + right.y)
    # the axle centre swings on a 0.3 m arm around the pin
    assert centre_x == pytest.approx(left.base_x - 0.3 + 0.3 * math.cos(angle))
    assert centre_y == pytest.approx(0.3 * math.sin(angle))


def test_straight_ahead_restores_base_positions(params: ParamSet) -> None:
    vehicle = _steered(params, 25.0)
    vehicle.steering.apply(0.0, vehicle.wheels)
    for wheel in vehicle.wheels:
        assert wheel.x == pytest.approx(wheel.base_x) and wheel.y == pytest.approx(wheel.base_y)
        assert wheel.steer == 0.0


def test_ackermann_axes_meet_on_the_rear_axle_line(params: ParamSet) -> None:
    params.set("steering.type", "ackermann")
    vehicle = _steered(params, 20.0)
    left, right, _ = vehicle.wheels
    assert left.steer > math.radians(20.0) > right.steer > 0.0  # inner wheel steers more
    assert (left.x, left.y) == (left.base_x, left.base_y)  # knuckle steering: no movement
    # turn radius seen from each wheel (to the centre line) must agree
    radius_left = WHEELBASE / math.tan(left.steer) + HALF_TRACK
    radius_right = WHEELBASE / math.tan(right.steer) - HALF_TRACK
    assert radius_left == pytest.approx(radius_right)
    assert radius_left == pytest.approx(WHEELBASE / math.tan(math.radians(20.0)))


def test_ackermann_zero_percent_is_parallel(params: ParamSet) -> None:
    params.set("steering.type", "ackermann")
    params.set("steering.ackermann_percentage", 0.0)
    vehicle = _steered(params, -18.0)
    left, right, _ = vehicle.wheels
    assert left.steer == right.steer == pytest.approx(math.radians(-18.0))


def test_ratio_and_lock(params: ParamSet) -> None:
    params.set("steering.ratio", 2.0)
    vehicle = _steered(params, 30.0)
    assert vehicle.steering.wheel_angle == pytest.approx(math.radians(15.0))
    vehicle.steering.apply(math.radians(500.0), vehicle.wheels)
    assert vehicle.steering.wheel_angle == pytest.approx(params.num("steering.max_angle"))
    assert vehicle.steering.max_handlebar_angle() == pytest.approx(
        2.0 * params.num("steering.max_angle"))
