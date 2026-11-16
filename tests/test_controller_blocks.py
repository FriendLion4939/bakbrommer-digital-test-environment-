"""Reference controller: each block on its own."""

import math

import pytest

from bakbrommer_twin.control.interface import ControllerInputs
from bakbrommer_twin.control.reference.engine_manager import CRANKING, OFF, RUNNING, EngineManager
from bakbrommer_twin.control.reference.estimator import SpeedEstimator
from bakbrommer_twin.control.reference.limits import PowerLimiter, StabilityLimiter
from bakbrommer_twin.control.reference.modes import ModeManager, ModeSettings
from bakbrommer_twin.control.reference.regen import Regen
from bakbrommer_twin.control.reference.slip import SlipLimiter
from bakbrommer_twin.control.reference.vectoring import TorqueVectoring
from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.params.definitions.control import RIDE_MODES

DT = 0.001
KMH = 1 / 3.6
RPM = 2 * math.pi / 60


def _inputs(speed: float, params: ParamSet, **fields: float) -> ControllerInputs:
    inputs = ControllerInputs(dt=DT, vehicle_speed=speed)
    inputs.wheel_speed_fl = inputs.wheel_speed_fr = speed / params.num("wheels.front_radius")
    inputs.wheel_speed_r = speed / params.num("wheels.rear_radius")
    for name, value in fields.items():
        setattr(inputs, name, value)
    return inputs


# ---- speed estimate ---------------------------------------------------------------------

def test_estimator_starts_at_wheel_speed_and_ignores_a_spinning_wheel(params: ParamSet) -> None:
    estimator = SpeedEstimator(params)
    inputs = _inputs(10.0, params)
    assert estimator.step(inputs, driving=True) == pytest.approx(10.0)
    inputs.wheel_speed_fl *= 2.0  # left wheel spins up
    for _ in range(500):
        estimator.step(inputs, driving=True)
    assert estimator.speed == pytest.approx(10.0)
    assert estimator.left == pytest.approx(20.0)


def test_estimator_ignores_a_locked_wheel_when_braking(params: ParamSet) -> None:
    estimator = SpeedEstimator(params)
    inputs = _inputs(10.0, params)
    estimator.step(inputs, driving=False)
    inputs.wheel_speed_fl = inputs.wheel_speed_fr = 0.0  # front wheels locked
    for _ in range(500):
        estimator.step(inputs, driving=False)
    assert estimator.speed == pytest.approx(10.0)


def test_estimator_is_rate_limited_by_the_accelerometer(params: ParamSet) -> None:
    estimator = SpeedEstimator(params)
    inputs = _inputs(10.0, params)
    estimator.step(inputs, driving=True)
    for name in ("wheel_speed_fl", "wheel_speed_fr", "wheel_speed_r"):
        setattr(inputs, name, 2.0 * getattr(inputs, name))  # all wheels spin, sensor too
    inputs.vehicle_speed = 20.0
    for _ in range(1000):  # one second, accelerometer says 0 m/s²
        estimator.step(inputs, driving=True)
    assert estimator.speed == pytest.approx(10.0 + params.num(
        "control.estimator_accel_margin") * 1.0, rel=0.01)


def test_estimator_removes_the_cornering_speed_difference(params: ParamSet) -> None:
    estimator = SpeedEstimator(params)
    yaw_rate, half_track = 0.5, params.num("geometry.front_track") / 2
    inputs = _inputs(8.0, params, gyro_z=yaw_rate)
    radius = params.num("wheels.front_radius")
    inputs.wheel_speed_fl = (8.0 - yaw_rate * half_track) / radius  # inner wheel slower
    inputs.wheel_speed_fr = (8.0 + yaw_rate * half_track) / radius
    estimator.step(inputs, driving=True)
    assert estimator.left == pytest.approx(8.0) and estimator.right == pytest.approx(8.0)
    assert estimator.speed == pytest.approx(8.0)


# ---- ride modes -----------------------------------------------------------------------------

def test_modes_are_read_from_the_parameters(params: ParamSet) -> None:
    manager = ModeManager(params)
    assert len(manager.table) == len(RIDE_MODES)
    sport = manager.table[RIDE_MODES.index("sport")]
    assert sport.electric_torque == params.num("control.mode_sport.electric_torque")
    assert manager.table[RIDE_MODES.index("standalone_electric")].engine_enabled is False
    assert manager.current.electric_torque == manager.table[0].electric_torque


def test_mode_change_glides_over_the_blend_time(params: ParamSet) -> None:
    manager = ModeManager(params)
    normal, sport = manager.table[0], manager.table[2]
    steps = round(params.num("control.mode_blend_time") / DT)
    for _ in range(steps // 2):
        current = manager.step(DT, 2.0)
    assert manager.active == 2
    halfway = 0.5 * (normal.electric_torque + sport.electric_torque)
    assert current.electric_torque == pytest.approx(halfway, rel=0.01)
    for _ in range(steps):
        current = manager.step(DT, 2.0)
    assert current.electric_torque == pytest.approx(sport.electric_torque)
    manager.step(DT, 99.0)  # out-of-range switch positions are clamped
    assert manager.active == len(RIDE_MODES) - 1
    assert manager.current.engine_enabled is False  # on/off settings switch at once


def test_inconsistent_mode_is_rejected(params: ParamSet) -> None:
    params.set_display("control.mode_eco.electric_fade_end", 10.0)
    with pytest.raises(ValueError, match="mode_eco"):
        ModeManager(params)


# ---- engine start/stop ----------------------------------------------------------------------

def _mode(start_speed: float = 0.0, enabled: bool = True) -> ModeSettings:
    mode = ModeSettings()
    mode.engine_start_speed, mode.engine_enabled = start_speed, enabled
    return mode


def test_engine_is_cranked_until_it_runs(params: ParamSet) -> None:
    manager = EngineManager(params)
    manager.step(DT, _mode(), 0.0, 0.0)
    assert manager.state == CRANKING
    manager.step(DT, _mode(), 0.0, 300 * RPM)
    assert manager.starter and manager.ignition
    manager.step(DT, _mode(), 0.0, 1500 * RPM)
    assert manager.state == RUNNING and manager.running
    manager.step(DT, _mode(), 0.0, 1500 * RPM)
    assert not manager.starter and manager.ignition


def test_failed_start_rests_then_retries(params: ParamSet) -> None:
    manager = EngineManager(params)
    for _ in range(round(params.num("control.engine_crank_timeout") / DT) + 5):
        manager.step(DT, _mode(), 0.0, 0.0)
    assert manager.state == OFF and not manager.starter
    for _ in range(round(params.num("control.engine_crank_pause") / DT) + 5):
        manager.step(DT, _mode(), 0.0, 0.0)
    assert manager.state == CRANKING


def test_engine_waits_for_start_speed_and_stops_with_delay_and_hysteresis(
        params: ParamSet) -> None:
    manager = EngineManager(params)
    eco = _mode(start_speed=15 * KMH)
    manager.step(DT, eco, 5 * KMH, 0.0)
    assert manager.state == OFF and not manager.ignition
    manager.step(DT, eco, 16 * KMH, 0.0)
    assert manager.state == CRANKING
    manager.step(DT, eco, 16 * KMH, 1500 * RPM)
    assert manager.running
    for _ in range(5000):  # 13 km/h: below start speed but inside the hysteresis band
        manager.step(DT, eco, 13 * KMH, 1500 * RPM)
    assert manager.running
    delay_steps = round(params.num("control.engine_stop_delay") / DT)
    for _ in range(delay_steps - 10):
        manager.step(DT, eco, 5 * KMH, 1500 * RPM)
    assert manager.running  # not yet
    for _ in range(20):
        manager.step(DT, eco, 5 * KMH, 1500 * RPM)
    assert manager.state == OFF and not manager.ignition


def test_electric_only_mode_switches_the_engine_off(params: ParamSet) -> None:
    manager = EngineManager(params)
    manager.step(DT, _mode(), 0.0, 1500 * RPM)  # already running at power-on
    assert manager.running
    for _ in range(round(params.num("control.engine_stop_delay") / DT) + 5):
        manager.step(DT, _mode(enabled=False), 10.0, 1500 * RPM)
    assert not manager.ignition and manager.state == OFF


def test_manual_start_mode_never_cranks(params: ParamSet) -> None:
    params.set("control.engine_auto_start_stop", False)
    manager = EngineManager(params)
    manager.step(DT, _mode(), 0.0, 0.0)
    assert manager.ignition and not manager.starter and not manager.running
    manager.step(DT, _mode(), 0.0, 1500 * RPM)
    assert manager.running
    manager.step(DT, _mode(enabled=False), 0.0, 1500 * RPM)
    assert not manager.ignition


# ---- slip limiter, vectoring, regen, limits -------------------------------------------------

def test_slip_limiter_cuts_on_spin_and_recovers(params: ParamSet) -> None:
    limiter = SlipLimiter(params, slip_target=0.12)
    assert limiter.step(DT, 10.5, 10.0, 1.0) == 0.0  # 5 % slip: fine
    first = limiter.step(DT, 14.0, 10.0, 1.0)  # 40 % slip
    assert first == pytest.approx(params.num("control.traction.proportional_gain") * 0.28,
                                  rel=0.05)
    for _ in range(200):
        cut = limiter.step(DT, 14.0, 10.0, 1.0)
    assert cut == 1.0
    for _ in range(100):
        cut = limiter.step(DT, 10.0, 10.0, 1.0)
    assert 0.0 < cut < 1.0  # recovering gradually
    for _ in range(2000):
        cut = limiter.step(DT, 10.0, 10.0, 1.0)
    assert cut == 0.0


def test_slip_limiter_watches_lock_with_negative_sign(params: ParamSet) -> None:
    limiter = SlipLimiter(params, slip_target=0.15)
    assert limiter.step(DT, 5.0, 10.0, -1.0) > 0.0  # wheel at half speed while braking
    limiter.reset()
    assert limiter.step(DT, 12.0, 10.0, -1.0) == 0.0  # a faster wheel is no lock


def test_vectoring_moves_torque_to_the_outer_wheel(params: ParamSet) -> None:
    params.set("control.vectoring.yaw_gain", 0.0)  # look at the load split alone
    vectoring = TorqueVectoring(params)
    vectoring.step(40.0, 8.0, 0.1, 0.5, 0.2 * 9.80665)  # left turn at 0.2 g
    share = params.num("control.vectoring.load_split_gain") * 0.2
    assert vectoring.left == pytest.approx(40.0 * (1 - share))
    assert vectoring.right == pytest.approx(40.0 * (1 + share))
    assert vectoring.left + vectoring.right == pytest.approx(80.0)  # the sum is kept
    vectoring.step(40.0, 8.0, -0.1, -0.5, -0.2 * 9.80665)  # right turn mirrors
    assert vectoring.left > vectoring.right
    vectoring.step(40.0, 8.0, 0.1, 0.5, 9.0)  # extreme: the inner wheel gets nothing
    assert vectoring.left == 0.0 and vectoring.right == pytest.approx(80.0)


def test_vectoring_yaw_correction(params: ParamSet) -> None:
    params.set("control.vectoring.load_split_gain", 0.0)
    vectoring = TorqueVectoring(params)
    speed, steer = 8.0, 0.1
    vectoring.step(40.0, speed, steer, 0.0, 0.0)  # steering left but not yet turning
    assert vectoring.yaw_reference > 0.0
    assert vectoring.right > vectoring.left  # push the vehicle into the turn
    vectoring.step(40.0, speed, steer, vectoring.yaw_reference, 0.0)
    assert vectoring.left == pytest.approx(vectoring.right)  # on target: no correction
    vectoring.step(40.0, speed, 0.0, 3.0, 0.0)  # spinning out to the left
    assert vectoring.left - vectoring.right == pytest.approx(
        params.num("control.vectoring.max_torque_difference"))


def test_vectoring_can_be_switched_off(params: ParamSet) -> None:
    params.set("control.vectoring.enabled", False)
    vectoring = TorqueVectoring(params)
    vectoring.step(40.0, 8.0, 0.3, 0.0, 3.0)
    assert vectoring.left == vectoring.right == 40.0


def test_regen_request(params: ParamSet) -> None:
    regen = Regen(params)
    mode = ModeSettings()
    mode.coast_regen_torque, mode.brake_regen_torque = 5.0, 30.0
    full = params.num("control.regen.full_pressure")
    threshold = params.num("control.regen.brake_threshold")
    assert regen.step(mode, 0.5, 0.0, 10.0, 66.0) == 0.0  # throttle open
    assert regen.step(mode, 0.0, 0.0, 10.0, 66.0) == pytest.approx(5.0)  # coasting
    assert regen.step(mode, 0.0, full, 10.0, 66.0) == pytest.approx(35.0)  # full brake
    assert regen.step(mode, 0.0, 0.5 * (full + threshold), 10.0, 66.0) == pytest.approx(20.0)
    assert regen.step(mode, 0.0, full, 2 * KMH, 66.0) == 0.0  # walking pace
    assert 0.0 < regen.step(mode, 0.0, full, 7 * KMH, 66.0) < 35.0  # fading in
    assert regen.step(mode, 0.0, full, 10.0, 71.5) == 0.0  # battery full
    assert 0.0 < regen.step(mode, 0.0, full, 10.0, 70.7) < 35.0


def test_power_limiter_prediction_and_feedback(params: ParamSet) -> None:
    limiter = PowerLimiter(params)
    limit = params.num("control.limits.battery_current")
    efficiency = params.num("control.limits.assumed_efficiency")
    allowed_power = limit * 66.0 * efficiency
    assert limiter.step(DT, True, 0.5 * allowed_power, 1.0, 66.0, 0.0, 30.0) == pytest.approx(1.0)
    assert limiter.step(DT, True, 2.0 * allowed_power, 1.0, 66.0, 0.0, 30.0) == pytest.approx(
        0.5, rel=0.01)
    assert limiter.step(DT, True, 2.0 * allowed_power, 0.5, 66.0, 0.0, 30.0) == pytest.approx(
        0.25, rel=0.01)  # a mode that may use half the limit
    for _ in range(300):  # measured current 20 % too high: the trim winds down
        factor = limiter.step(DT, True, 0.5 * allowed_power, 1.0, 66.0, 1.2 * limit, 30.0)
    assert factor < 0.8
    for _ in range(3000):  # and recovers when the current is low again
        factor = limiter.step(DT, True, 0.5 * allowed_power, 1.0, 66.0, 0.2 * limit, 30.0)
    assert factor == pytest.approx(1.0)


def test_power_limiter_voltage_temperature_and_regen(params: ParamSet) -> None:
    limiter = PowerLimiter(params)
    assert limiter.step(DT, True, 100.0, 1.0, 61.0, 0.0, 30.0) == pytest.approx(0.5, abs=0.01)
    assert limiter.step(DT, True, 100.0, 1.0, 59.0, 0.0, 30.0) == 0.0
    limiter.reset()
    assert limiter.step(DT, True, 100.0, 1.0, 66.0, 0.0, 115.0) == pytest.approx(0.5, abs=0.01)
    assert limiter.step(DT, True, 100.0, 1.0, 66.0, 0.0, 140.0) == 0.0
    limiter.reset()
    charge = params.num("control.limits.charge_current")
    efficiency = params.num("control.limits.assumed_efficiency")
    regen_power = -2.0 * charge * 66.0 / efficiency  # would charge at twice the limit
    factor = limiter.step(DT, False, regen_power, 1.0, 66.0, 0.0, 30.0)
    assert factor == pytest.approx(0.5, rel=0.01)
    # a low battery does not stop regen
    assert limiter.step(DT, False, regen_power, 1.0, 55.0, 0.0, 30.0) > 0.0


def test_stability_limiter(params: ParamSet) -> None:
    limiter = StabilityLimiter(params)
    start, end = (params.num("control.stability.accel_start"),
                  params.num("control.stability.accel_end"))
    minimum = params.num("control.stability.min_torque_factor")
    assert limiter.step(DT, 0.5 * start, 0.0) == 1.0
    assert limiter.step(DT, -0.5 * (start + end), 0.0) == pytest.approx(0.5 * (1 + minimum))
    assert limiter.step(DT, 2.0 * end, 0.0) == pytest.approx(minimum)
    assert limiter.step(DT, 0.0, 1.0) == pytest.approx(minimum)  # roll rate trigger
    assert limiter.step(DT, 0.0, 0.0) == pytest.approx(minimum)  # held
    for _ in range(round(params.num("control.stability.hold_time") / DT) + 5):
        factor = limiter.step(DT, 0.0, 0.0)
    assert factor == 1.0
    params.set("control.stability.enabled", False)
    assert StabilityLimiter(params).step(DT, 99.0, 9.0) == 1.0
