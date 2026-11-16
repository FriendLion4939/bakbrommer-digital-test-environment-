"""Petrol engine, centrifugal clutch and gearbox."""

import math

import pytest

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.physics.engine import Engine
from bakbrommer_twin.physics.gearbox import NEUTRAL, Driveline

DT = 0.001
RPM = 2.0 * math.pi / 60.0


def _free_run(engine: Engine, throttle: float, seconds: float, ignition: bool = True,
              starter: bool = False) -> None:
    """Engine with an open clutch: integrate its own speed."""
    for _ in range(round(seconds / DT)):
        engine.update(DT, throttle, ignition, starter)
        engine.speed = max(0.0, engine.speed + DT * engine.torque / engine.inertia)


def test_full_throttle_torque_matches_the_curve(params: ParamSet) -> None:
    engine = Engine(params)
    engine.speed = 5500 * RPM
    for _ in range(1000):  # hold the speed, let the load settle
        engine.update(DT, 1.0, True, False)
    assert engine.torque == pytest.approx(7.0, rel=1e-3)


def test_closed_throttle_brakes(params: ParamSet) -> None:
    engine = Engine(params)
    engine.speed = 6000 * RPM
    for _ in range(1000):
        engine.update(DT, 0.0, True, False)
    assert engine.torque == pytest.approx(-engine.friction(engine.speed), rel=1e-3)


def test_idles_near_idle_speed(params: ParamSet) -> None:
    engine = Engine(params)
    engine.start_running()
    _free_run(engine, 0.0, 5.0)
    assert engine.running
    assert engine.speed == pytest.approx(engine.idle_speed, rel=0.05)


def test_rev_limiter(params: ParamSet) -> None:
    engine = Engine(params)
    engine.start_running()
    _free_run(engine, 1.0, 5.0)
    assert engine.speed == pytest.approx(engine.rev_limit, rel=0.03)


def test_starter_starts_and_ignition_stops(params: ParamSet) -> None:
    engine = Engine(params)
    _free_run(engine, 0.0, 1.0)  # nothing happens without the starter
    assert engine.speed == 0.0 and not engine.running
    _free_run(engine, 0.0, 2.0, starter=True)
    assert engine.running
    _free_run(engine, 0.0, 3.0)
    assert engine.speed == pytest.approx(engine.idle_speed, rel=0.05)
    _free_run(engine, 0.0, 5.0, ignition=False)
    assert engine.speed == 0.0 and not engine.running
    assert engine.fuel_rate == 0.0


def test_fuel_consumption_is_plausible(params: ParamSet) -> None:
    engine = Engine(params)
    engine.speed = 5500 * RPM
    for _ in range(1000):
        engine.update(DT, 1.0, True, False)
    power = engine.torque * engine.speed
    bsfc = engine.fuel_rate / power * 3.6e9  # g/kWh
    assert 250.0 < bsfc < 450.0
    engine.speed = engine.idle_speed
    for _ in range(1000):
        engine.update(DT, 0.0, True, False)
    litres_per_hour = engine.fuel_rate / engine.fuel_density * 1000 * 3600
    assert 0.05 < litres_per_hour < 0.5


def test_total_ratio_and_gear_count(params: ParamSet) -> None:
    driveline = Driveline(params)
    assert driveline.gear_count == 4
    assert driveline.total_ratio(1) == pytest.approx(4.059 * 2.833 * 2.57)


def test_clutch_capacity_grows_between_engage_and_lockup(params: ParamSet) -> None:
    driveline = Driveline(params)
    caps = []
    for rpm in (1500, 2300, 3000, 3800, 6000):
        driveline.update(DT, 1, rpm * RPM, 0.0, 0.0)
        caps.append(driveline.capacity)
    assert caps[0] == 0.0 and caps[1] == pytest.approx(0.0, abs=1e-9)
    assert 0.0 < caps[2] < caps[3]
    assert caps[3] == pytest.approx(driveline.clutch_max) == caps[4]


def test_gear_change_interrupts_drive(params: ParamSet) -> None:
    driveline = Driveline(params)
    driveline.update(DT, 2, 6000 * RPM, 10.0, 1.0)
    assert driveline.shifting and driveline.capacity == 0.0 and driveline.gear == 1
    for _ in range(round(driveline.shift_time / DT) + 1):
        driveline.update(DT, 2, 6000 * RPM, 10.0, 1.0)
    assert not driveline.shifting and driveline.gear == 2
    assert driveline.ratio == pytest.approx(driveline.total_ratio(2))
    assert driveline.capacity > 0.0
    driveline.select_gear(NEUTRAL)
    driveline.update(DT, NEUTRAL, 6000 * RPM, 10.0, 1.0)
    assert driveline.capacity == 0.0


def test_clutch_locks_engine_to_wheel(params: ParamSet) -> None:
    driveline = Driveline(params)
    engine_speed, wheel_speed = 5000 * RPM, 5.0
    for _ in range(3000):  # no engine torque, free wheel with large inertia
        driveline.update(DT, 1, engine_speed, wheel_speed, 0.0)
        engine_speed, wheel_speed = driveline.solve(
            DT, engine_speed, 0.0, 0.012, wheel_speed, 5.0, 0.0, 0.0)
    assert engine_speed == pytest.approx(driveline.ratio * wheel_speed, rel=1e-6)
    assert driveline.clutch_loss == pytest.approx(0.0, abs=1e-6)


def test_slipping_clutch_transmits_its_capacity_with_efficiency(params: ParamSet) -> None:
    driveline = Driveline(params)
    driveline.update(DT, 1, 6000 * RPM, 0.0, 1.0)
    driveline.solve(DT, 6000 * RPM, 7.0, 0.012, 0.0, 1e9, 0.0, 0.0)
    assert driveline.clutch_torque == pytest.approx(driveline.clutch_max)
    assert driveline.wheel_torque == pytest.approx(
        driveline.clutch_max * driveline.ratio * driveline.efficiency)
    assert driveline.clutch_loss > 0.0


def test_friction_holds_a_wheel_and_never_reverses_it(params: ParamSet) -> None:
    driveline = Driveline(params)
    driveline.select_gear(NEUTRAL)
    driveline.update(DT, NEUTRAL, 0.0, 0.0, 0.0)
    # 50 Nm tries to turn the wheel, 80 Nm of brake holds it exactly still
    _, wheel = driveline.solve(DT, 0.0, 0.0, 0.012, 0.0, 0.35, 50.0, 80.0)
    assert wheel == 0.0 and driveline.friction_torque == pytest.approx(50.0)
    # a spinning wheel is stopped but not reversed
    wheel = 0.2
    for _ in range(20):
        _, wheel = driveline.solve(DT, 0.0, 0.0, 0.012, wheel, 0.35, 0.0, 80.0)
    assert wheel == 0.0


def test_cvt_ratio_follows_engine_speed_target(params: ParamSet) -> None:
    params.set("gearbox.type", "cvt")
    driveline = Driveline(params)
    assert driveline.gear_count == 1
    assert driveline.cvt_ratio == pytest.approx(driveline.cvt_low)
    wheel_speed = 60.0  # fast: the belt should shift towards the high gear
    for _ in range(5000):
        driveline.update(DT, 1, 7000 * RPM, wheel_speed, 1.0)
    wanted = driveline.cvt_speed_full / (wheel_speed * driveline.primary * driveline.final)
    assert driveline.cvt_ratio == pytest.approx(
        max(driveline.cvt_high, min(driveline.cvt_low, wanted)), rel=1e-3)


def test_inconsistent_clutch_parameters_are_rejected(params: ParamSet) -> None:
    params.set("clutch.lockup_speed", params.num("clutch.engage_speed") * 0.9)
    with pytest.raises(ValueError, match="lockup_speed"):
        Driveline(params)
