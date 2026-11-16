"""Brakes and aerodynamics."""

import pytest

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.physics import mass
from bakbrommer_twin.physics.aero import Aero, drag_area
from bakbrommer_twin.physics.brakes import Brakes

DT = 0.001


def test_brake_torque_formula(params: ParamSet) -> None:
    brakes = Brakes(params)
    for _ in range(1000):
        brakes.update(DT, 1.0, 0.5)
    # T = 2·μ·A·p·r with the default front values: 2 × 0.40 × 9.8 cm² × 60 bar × 90 mm
    assert brakes.front_torque == pytest.approx(2 * 0.40 * 9.8e-4 * 60e5 * 0.090, rel=1e-3)
    assert brakes.front_torque == pytest.approx(brakes.max_front_torque(), rel=1e-3)
    assert brakes.rear_torque == pytest.approx(0.5 * brakes.max_rear_torque(), rel=1e-3)


def test_pressure_builds_with_lag_and_releases(params: ParamSet) -> None:
    brakes = Brakes(params)
    brakes.update(DT, 1.0, 0.0)
    assert 0.0 < brakes.front_pressure < brakes.front_max_pressure
    assert brakes.rear_pressure == 0.0
    for _ in range(2000):
        brakes.update(DT, 0.0, 0.0)
    assert brakes.front_torque == pytest.approx(0.0, abs=1e-6)


def test_linked_brakes_feed_both_circuits(params: ParamSet) -> None:
    params.set("brakes.linked", True)
    brakes = Brakes(params)
    for _ in range(1000):
        brakes.update(DT, 0.0, 1.0)  # rear lever only
    assert brakes.front_pressure == pytest.approx(brakes.front_max_pressure, rel=1e-3)
    assert brakes.rear_pressure == pytest.approx(
        params.num("brakes.linked_rear_share") * brakes.rear_max_pressure, rel=1e-3)


def test_drag_formula_and_power(params: ParamSet) -> None:
    aero = Aero(params, mass.mass_properties(params))
    aero.update(20.0, 0.0, 0.0, 0.0)
    expected = 0.5 * 1.225 * drag_area(params) * 20.0**2
    assert aero.fx == pytest.approx(-expected)
    assert aero.fy == 0.0
    assert aero.power == pytest.approx(expected * 20.0)


def test_headwind_and_tailwind(params: ParamSet) -> None:
    aero = Aero(params, mass.mass_properties(params))
    aero.update(10.0, 0.0, -5.0, 0.0)  # air coming at the vehicle
    head = aero.fx
    aero.update(10.0, 0.0, 5.0, 0.0)  # air moving with the vehicle
    tail = aero.fx
    assert head == pytest.approx(9.0 * tail)  # (15/5)² = 9
    aero.update(0.0, 0.0, 10.0, 0.0)  # standing in a tailwind: pushed forwards
    assert aero.fx > 0.0


def test_cross_wind_pushes_and_rolls(params: ParamSet) -> None:
    aero = Aero(params, mass.mass_properties(params))
    aero.update(10.0, 0.0, 0.0, -8.0)  # wind blowing towards the right
    assert aero.fy < 0.0
    assert aero.mx * aero.arm_z > 0.0  # force above the CoG rolls the body with the wind
    assert aero.mz == pytest.approx(aero.arm_x * aero.fy)


def test_box_shape_selects_drag_coefficient(params: ParamSet) -> None:
    params.set("aero.cargo_box_shape", "streamlined")
    assert drag_area(params) == pytest.approx(
        params.num("aero.cd_streamlined") * params.num("aero.frontal_area"))
