"""Whole-vehicle sanity checks: equilibrium, coasting, parking, energy, momentum."""

import math
from itertools import pairwise

import pytest
from helpers import Rig

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.physics import mass


def test_rest_equilibrium_matches_static_loads(quiet: ParamSet) -> None:
    rig = Rig(quiet)
    rig.run(3.0)
    chassis = rig.vehicle.chassis
    for wheel, expected in zip(rig.vehicle.wheels, mass.static_wheel_loads(quiet), strict=True):
        assert wheel.load == pytest.approx(expected, rel=1e-4)
    assert chassis.z == pytest.approx(rig.vehicle.props.cog_height, abs=1e-5)
    assert abs(chassis.pitch) < 1e-5 and abs(chassis.roll) < 1e-9
    assert abs(chassis.u) < 1e-4


def test_sideways_cargo_tilts_the_loads_not_the_body(quiet: ParamSet) -> None:
    quiet.set("mass.cargo.mass", 60.0)
    quiet.set("mass.cargo.y", 0.15)
    rig = Rig(quiet)
    rig.run(3.0)
    left, right, _ = (w.load for w in rig.vehicle.wheels)
    assert left > right
    assert left - right == pytest.approx(
        mass.static_wheel_loads(quiet)[0] - mass.static_wheel_loads(quiet)[1], rel=1e-3)
    assert abs(rig.vehicle.chassis.roll) < 1e-4  # springs are pre-loaded for the static case


def test_dropped_vehicle_settles(quiet: ParamSet) -> None:
    rig = Rig(quiet)
    rig.vehicle.chassis.z += 0.10  # lift it 10 cm and let go
    rig.run(0.05)
    assert all(wheel.load == 0.0 and wheel.gap > 0.0 for wheel in rig.vehicle.wheels)
    rig.run(4.0)
    total = sum(wheel.load for wheel in rig.vehicle.wheels)
    assert total == pytest.approx(rig.vehicle.props.mass * mass.GRAVITY, rel=1e-3)


def test_coasting_vehicle_slows_down(quiet: ParamSet) -> None:
    rig = Rig(quiet, speed=15.0, gear=0, engine_running=False)
    speeds = []
    for _ in range(10):
        rig.run(1.0)
        speeds.append(rig.vehicle.speed())
    assert all(later < earlier for earlier, later in pairwise(speeds))
    assert 5.0 < speeds[-1] < 14.0


def test_coast_down_deceleration_matches_hand_calculation(quiet: ParamSet) -> None:
    quiet.set("motor.drag_torque_static", 0.0)
    quiet.set("motor.drag_torque_speed", 0.0)
    quiet.set("gearbox.drag_torque", 0.0)
    rig = Rig(quiet, speed=15.0, gear=0, engine_running=False)
    rig.run(1.0)
    before = rig.vehicle.speed()
    rig.run(0.5)
    v = 0.5 * (before + rig.vehicle.speed())
    measured = (before - rig.vehicle.speed()) / 0.5
    m = rig.vehicle.props.mass
    rolling = 0.015 * (1.0 + 1.5e-4 * v * v) * m * mass.GRAVITY
    drag = 0.5 * 1.225 * 1.05 * 1.0 * v * v
    # the three wheels' rotational inertia adds to the mass that has to be slowed
    inertia_mass = 2 * 0.25 / 0.235**2 + 0.35 / 0.29**2
    assert measured == pytest.approx((rolling + drag) / (m + inertia_mass), rel=0.01)


def test_parked_on_slope_with_brakes_stays_put(quiet: ParamSet) -> None:
    rig = Rig(quiet, engine_running=False)
    rig.set_grade(15.0)
    rig.rider.brake_front = rig.rider.brake_rear = 1.0
    rig.run(2.0)  # settle onto the tyres
    start = rig.vehicle.chassis.x
    rig.run(10.0)
    assert abs(rig.vehicle.chassis.x - start) < 1e-4
    assert all(wheel.omega == 0.0 for wheel in rig.vehicle.wheels)


def test_released_on_slope_rolls_downhill(quiet: ParamSet) -> None:
    rig = Rig(quiet, gear=0, engine_running=False)
    rig.set_grade(15.0)
    rig.run(3.0)
    assert rig.vehicle.speed() < -1.0


def test_gentle_slope_is_held_by_rolling_resistance(quiet: ParamSet) -> None:
    rig = Rig(quiet, gear=0, engine_running=False)
    rig.set_grade(0.5)  # less than the rolling resistance coefficient of 1.5 %
    rig.run(5.0)
    assert abs(rig.vehicle.speed()) < 1e-3


def test_acceleration_shifts_load_to_the_rear(quiet: ParamSet) -> None:
    rig = Rig(quiet)
    static = mass.static_wheel_loads(quiet)
    rig.commands.torque_left = rig.commands.torque_right = 60.0
    rig.run(1.0)
    props, wheelbase = rig.vehicle.props, quiet.num("geometry.wheelbase")
    accel = rig.vehicle.chassis.accel_x
    assert accel > 1.0
    # ΔF_rear = m·a·h/L (moment balance about the front contact line)
    expected = props.mass * accel * props.cog_height / wheelbase
    assert rig.vehicle.wheels[2].load - static[2] == pytest.approx(expected, rel=0.08)


def test_braking_shifts_load_to_the_front_and_pitches_nose_down(quiet: ParamSet) -> None:
    rig = Rig(quiet, speed=12.0, gear=0, engine_running=False)
    static = mass.static_wheel_loads(quiet)
    rig.rider.brake_front = 0.25
    rig.run(1.0)
    assert rig.vehicle.wheels[0].load > static[0]
    assert rig.vehicle.wheels[2].load < static[2]
    assert rig.vehicle.chassis.pitch > 0.0  # positive pitch = nose down
    assert rig.vehicle.chassis.accel_x < -1.0


def test_mechanical_energy_balance_closes(quiet: ParamSet) -> None:
    rig = Rig(quiet)
    vehicle = rig.vehicle
    start = vehicle.mechanical_energy()
    rig.rider.throttle = 1.0
    rig.commands.torque_left = rig.commands.torque_right = 30.0
    rig.run(8.0)
    rig.rider.throttle = 0.0
    rig.commands.torque_left = rig.commands.torque_right = 0.0
    rig.rider.brake_front, rig.rider.brake_rear = 0.15, 0.2
    rig.run(3.0)
    ledger = vehicle.energy
    error = ledger.mechanical_error(start, vehicle.mechanical_energy())
    assert ledger.mechanical_input() > 20_000.0
    assert abs(error) < 0.005 * ledger.mechanical_input()
    assert ledger.brake_loss > 0.0 and ledger.aero_loss > 0.0 and ledger.rolling_loss > 0.0


def test_electrical_energy_balance_closes(quiet: ParamSet) -> None:
    rig = Rig(quiet, gear=0, engine_running=False)
    rig.commands.torque_left = rig.commands.torque_right = 40.0
    rig.run(10.0)
    ledger = rig.vehicle.energy
    # chemical energy = bus energy + aux + losses inside the pack
    balance = ledger.bus_energy + ledger.aux_energy + ledger.battery_loss
    assert ledger.battery_chemical == pytest.approx(balance, rel=0.01)
    # bus energy = motor work + copper loss + controller loss; so it must exceed the first two
    assert ledger.bus_energy > ledger.motor_work + ledger.motor_loss > 0.0


def test_momentum_change_equals_impulse(quiet: ParamSet) -> None:
    rig = Rig(quiet, speed=8.0)
    chassis = rig.vehicle.chassis
    vx0, vy0 = chassis.world_velocity()
    rig.rider.steer = math.radians(6.0)  # drive a curve so both world axes are involved
    rig.rider.throttle = 0.6
    rig.commands.torque_left, rig.commands.torque_right = 20.0, 35.0
    rig.run(4.0)
    vx1, vy1 = chassis.world_velocity()
    m = chassis.mass
    assert abs(chassis.yaw) > 0.5  # it really turned
    assert m * (vx1 - vx0) == pytest.approx(chassis.impulse_x, abs=0.01 * m * 8.0)
    assert m * (vy1 - vy0) == pytest.approx(chassis.impulse_y, abs=0.01 * m * 8.0)


def test_uphill_costs_gravity_work(quiet: ParamSet) -> None:
    rig = Rig(quiet, speed=10.0)
    rig.set_grade(8.0)
    rig.rider.throttle = 1.0
    rig.commands.torque_left = rig.commands.torque_right = 30.0
    rig.run(5.0)
    climbed = rig.vehicle.chassis.x * rig.env.grade_sin
    expected = -rig.vehicle.props.mass * mass.GRAVITY * climbed
    assert rig.vehicle.energy.gravity_work == pytest.approx(expected, rel=0.01)


@pytest.mark.parametrize("step_ms", [0.5, 2.0])
def test_result_is_stable_for_other_time_steps(quiet: ParamSet, step_ms: float) -> None:
    def speed_after(step: float) -> float:
        quiet.set_display("sim.time_step", step)
        rig = Rig(quiet)
        rig.rider.throttle = 1.0
        rig.commands.torque_left = rig.commands.torque_right = 40.0
        rig.run(5.0)
        return rig.vehicle.speed()

    assert speed_after(step_ms) == pytest.approx(speed_after(1.0), rel=0.01)
