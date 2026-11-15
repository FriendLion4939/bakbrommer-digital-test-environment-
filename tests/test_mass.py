"""Mass properties, static wheel loads and rigid-vehicle stability limits."""

import math

import pytest

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.params.derived import derived_dict
from bakbrommer_twin.physics import mass

G = mass.GRAVITY


def _single_mass(params: ParamSet, m: float, x: float, y: float, h: float) -> ParamSet:
    """Put all mass in the chassis component as a point mass."""
    for key in mass.COMPONENTS:
        params.set(f"mass.{key}.mass", 0.0)
    params.set("mass.chassis.mass", m)
    params.set("mass.chassis.x", x)
    params.set("mass.chassis.y", y)
    params.set("mass.chassis.height", h)
    return params


def test_total_and_cog_hand_calculation(params: ParamSet) -> None:
    props = mass.mass_properties(params)
    assert props.mass == pytest.approx(130 + 14 + 80 + 0 + 3)
    expected_x = (130 * 0.85 + 14 * 0.90 + 80 * 1.15 + 3 * 1.20) / 227
    assert props.cog_x == pytest.approx(expected_x)


def test_cargo_moves_cog_forward_and_changes_height(params: ParamSet) -> None:
    empty = mass.mass_properties(params)
    params.set("mass.cargo.mass", 80.0)
    params.set("mass.cargo.height", 0.9)
    loaded = mass.mass_properties(params)
    assert loaded.cog_x < empty.cog_x
    assert loaded.cog_height > empty.cog_height


def test_parallel_axis_two_point_masses(params: ParamSet) -> None:
    for key in mass.COMPONENTS:
        params.set(f"mass.{key}.mass", 0.0)
    for key, x in (("battery", 0.0), ("fuel", 2.0)):
        params.set(f"mass.{key}.mass", 10.0)
        params.set(f"mass.{key}.x", x)
        params.set(f"mass.{key}.height", 0.5)
    props = mass.mass_properties(params)
    assert props.cog_x == pytest.approx(1.0)
    assert props.inertia_yaw == pytest.approx(2 * 10.0 * 1.0**2)
    assert props.inertia_pitch == pytest.approx(20.0)
    assert props.inertia_roll == pytest.approx(0.0)


def test_static_loads_sum_to_weight_and_follow_offsets(params: ParamSet) -> None:
    fl, fr, rear = mass.static_wheel_loads(params)
    assert fl + fr + rear == pytest.approx(mass.mass_properties(params).mass * G)
    assert fl == pytest.approx(fr)
    params.set("mass.cargo.mass", 50.0)
    params.set("mass.cargo.y", 0.2)
    fl, fr, _ = mass.static_wheel_loads(params)
    assert fl > fr


def test_static_loads_simple_case(params: ParamSet) -> None:
    _single_mass(params, 100.0, 0.4, 0.0, 0.5)  # a quarter of the 1.6 m wheelbase
    fl, fr, rear = mass.static_wheel_loads(params)
    assert rear == pytest.approx(100 * G * 0.25)
    assert fl == pytest.approx(100 * G * 0.375)
    assert fr == pytest.approx(fl)


def test_lift_threshold_matches_textbook_formula(params: ParamSet) -> None:
    _single_mass(params, 200.0, 0.8, 0.0, 0.6)
    half_track = params.num("geometry.front_track") / 2
    expected = G * half_track * (1 - 0.8 / 1.6) / 0.6
    assert mass.lift_threshold_accel(params, turn_left=True) == pytest.approx(expected)
    assert mass.lift_threshold_accel(params, turn_left=False) == pytest.approx(expected)


def test_sideways_offset_makes_one_direction_worse(params: ParamSet) -> None:
    _single_mass(params, 200.0, 0.8, 0.05, 0.6)
    left = mass.lift_threshold_accel(params, turn_left=True)
    right = mass.lift_threshold_accel(params, turn_left=False)
    assert left > right
    assert left - right == pytest.approx(2 * G * 0.05 / 0.6)


def test_tip_over_angle(params: ParamSet) -> None:
    _single_mass(params, 200.0, 0.8, 0.0, 0.6)
    half_track = params.num("geometry.front_track") / 2
    distance = 0.8 * half_track / math.hypot(1.6, half_track)
    assert mass.tip_over_angle(params) == pytest.approx(math.atan(distance / 0.6))


def test_higher_load_lowers_stability(params: ParamSet) -> None:
    params.set("mass.cargo.mass", 80.0)
    params.set("mass.cargo.height", 0.5)
    low = derived_dict(params)
    params.set("mass.cargo.height", 1.0)
    high = derived_dict(params)
    assert high["lift_accel_left_turn"] < low["lift_accel_left_turn"]
    assert high["tip_over_angle"] < low["tip_over_angle"]


def test_zero_mass_is_an_error(params: ParamSet) -> None:
    for key in mass.COMPONENTS:
        params.set(f"mass.{key}.mass", 0.0)
    with pytest.raises(ValueError, match="greater than zero"):
        mass.mass_properties(params)
