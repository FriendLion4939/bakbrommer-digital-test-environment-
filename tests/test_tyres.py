"""Tyre model: force curve shape, combined slip, load sensitivity, relaxation."""

import math

import pytest

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.physics.surfaces import Surface, load_surfaces
from bakbrommer_twin.physics.tyres import Tyre, force_curve

DT = 0.001


def _settle(tyre: Tyre, surface: Surface, v_long: float, v_lat: float, rim: float,
            load: float, seconds: float = 2.0) -> None:
    for _ in range(round(seconds / DT)):
        tyre.update(DT, v_long, v_lat, rim, load, surface)


@pytest.fixture
def dry(params: ParamSet) -> Surface:
    return load_surfaces(params)["dry_asphalt"]


@pytest.fixture
def tyre(params: ParamSet) -> Tyre:
    return Tyre(params, "front")


def test_curve_peaks_at_one_and_tends_to_slide_ratio(params: ParamSet, dry: Surface) -> None:
    assert force_curve(dry, 1.0) == pytest.approx(1.0)
    assert force_curve(dry, 0.9) < 1.0 and force_curve(dry, 1.1) < 1.0
    assert force_curve(dry, 1e6) == pytest.approx(
        params.num("surface.dry_asphalt.slide_ratio"), rel=1e-3)


def test_every_surface_has_a_valid_shape(params: ParamSet) -> None:
    for surface in load_surfaces(params).values():
        assert 1.0 < surface.shape < 2.0
        assert surface.stiffness > 0.0
        assert force_curve(surface, 1.0) == pytest.approx(1.0)


def test_steady_longitudinal_force_at_peak_slip(tyre: Tyre, dry: Surface) -> None:
    speed, load = 10.0, tyre.nominal_load
    _settle(tyre, dry, speed, 0.0, speed * (1.0 + tyre.kappa_peak), load)
    assert tyre.kappa == pytest.approx(tyre.kappa_peak, rel=1e-3)
    assert tyre.fx == pytest.approx(dry.friction * load, rel=1e-3)
    assert tyre.fy == 0.0


def test_steady_lateral_force_at_peak_slip_angle(params: ParamSet, tyre: Tyre,
                                                 dry: Surface) -> None:
    speed, load = 10.0, tyre.nominal_load
    angle = params.num("tyre.front.slip_angle_at_peak")
    _settle(tyre, dry, speed, -speed * math.tan(angle), speed, load)
    assert math.atan(tyre.tan_alpha) == pytest.approx(angle, rel=1e-3)
    assert tyre.fy == pytest.approx(dry.friction * tyre.lat_ratio * load, rel=1e-3)


def test_force_opposes_sliding(tyre: Tyre, dry: Surface) -> None:
    _settle(tyre, dry, 10.0, 0.5, 9.0, 800.0)  # braking, sliding to the left
    assert tyre.fx < 0.0 and tyre.fy < 0.0


def test_combined_slip_stays_inside_friction_ellipse(tyre: Tyre, dry: Surface) -> None:
    load = tyre.nominal_load
    limit = dry.friction * load
    for rim, v_lat in [(11.0, -1.0), (12.0, -3.0), (8.0, 2.0), (15.0, -0.5)]:
        _settle(tyre, dry, 10.0, v_lat, rim, load)
        usage = math.hypot(tyre.fx / limit, tyre.fy / (limit * tyre.lat_ratio))
        assert usage <= 1.0 + 1e-9
    # heavy combined slip leaves less sideways grip than pure cornering
    _settle(tyre, dry, 10.0, -1.0, 10.0, load)
    pure = tyre.fy
    _settle(tyre, dry, 10.0, -1.0, 13.0, load)
    assert tyre.fy < 0.7 * pure


def test_load_sensitivity(tyre: Tyre, dry: Surface) -> None:
    speed = 10.0
    rim = speed * (1.0 + tyre.kappa_peak)
    _settle(tyre, dry, speed, 0.0, rim, tyre.nominal_load)
    mu_nominal = tyre.fx / tyre.nominal_load
    _settle(tyre, dry, speed, 0.0, rim, 2.0 * tyre.nominal_load)
    mu_double = tyre.fx / (2.0 * tyre.nominal_load)
    assert mu_double == pytest.approx(mu_nominal / (1.0 + tyre.load_sensitivity), rel=1e-3)


def test_wet_surface_gives_less_force(params: ParamSet, tyre: Tyre, dry: Surface) -> None:
    wet = load_surfaces(params)["wet_asphalt"]
    rim = 10.0 * (1.0 + tyre.kappa_peak)
    _settle(tyre, dry, 10.0, 0.0, rim, 800.0)
    dry_force = tyre.fx
    _settle(tyre, wet, 10.0, 0.0, rim, 800.0)
    assert tyre.fx == pytest.approx(dry_force * wet.friction / dry.friction, rel=0.02)


def test_relaxation_builds_force_over_the_relaxation_length(tyre: Tyre, dry: Surface) -> None:
    speed, slip = 10.0, 0.01  # small slip: linear range
    steps = round(tyre.sigma_long / speed / DT)  # time to roll one relaxation length
    for _ in range(steps):
        tyre.update(DT, speed, 0.0, speed * (1.0 + slip), 800.0, dry)
    # first-order lag: 1 − 1/e ≈ 63 % after one relaxation length
    assert tyre.kappa / slip == pytest.approx(1.0 - math.exp(-1.0), abs=0.03)


def test_standstill_acts_like_a_spring(tyre: Tyre, dry: Surface) -> None:
    # Vehicle creeps backwards 1 mm with the wheel held: force pushes it forwards again.
    for _ in range(10):
        tyre.update(DT, -0.1, 0.0, 0.0, 800.0, dry)
    tyre.update(DT, 0.0, 0.0, 0.0, 800.0, dry)
    assert tyre.kappa == pytest.approx(0.001 / tyre.sigma_long, rel=0.01)
    assert tyre.fx > 0.0
    held = tyre.fx
    for _ in range(1000):  # nothing moves: the force must stay, not leak away
        tyre.update(DT, 0.0, 0.0, 0.0, 800.0, dry)
    assert tyre.fx == pytest.approx(held)


def test_lifted_wheel_has_no_force(tyre: Tyre, dry: Surface) -> None:
    _settle(tyre, dry, 10.0, -1.0, 12.0, 800.0, seconds=0.5)
    tyre.update(DT, 10.0, -1.0, 12.0, 0.0, dry)
    assert (tyre.fx, tyre.fy, tyre.kappa, tyre.tan_alpha) == (0.0, 0.0, 0.0, 0.0)


def test_slip_state_is_limited(tyre: Tyre, dry: Surface) -> None:
    _settle(tyre, dry, 0.0, 0.0, 30.0, 800.0, seconds=1.0)  # burnout at standstill
    assert tyre.kappa == pytest.approx(tyre.slip_limit)
