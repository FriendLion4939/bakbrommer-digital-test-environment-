"""Electric drive: torque limits, losses, regeneration, thermal behaviour."""

import pytest

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.physics.motors import ElectricDrive

DT = 0.001
V_BUS = 66.0
AIR = 20.0


def _run(drive: ElectricDrive, command: float, omega: float, seconds: float = 0.5,
         bus_on: bool = True) -> None:
    for _ in range(round(seconds / DT)):
        drive.step(DT, command, omega, V_BUS, bus_on, AIR)


@pytest.fixture
def drive(params: ParamSet) -> ElectricDrive:
    params.set("motor.line_current_limit", 150.0)  # look at the motor, not the fuse
    return ElectricDrive(params)


def test_follows_command_with_lag(drive: ElectricDrive) -> None:
    drive.step(DT, 30.0, 10.0, V_BUS, True, AIR)
    assert 0.0 < drive.torque < 30.0
    _run(drive, 30.0, 10.0)
    assert drive.torque == pytest.approx(30.0, rel=1e-3)


def test_peak_torque_is_phase_current_limit(drive: ElectricDrive) -> None:
    _run(drive, 500.0, 5.0)
    assert drive.torque == pytest.approx(drive.kt * drive.peak_current, rel=1e-3)


def test_voltage_limit_ends_at_no_load_speed(drive: ElectricDrive) -> None:
    no_load = drive.modulation * V_BUS * drive.field_weakening / drive.ke
    assert drive.max_drive_torque(no_load * 1.01, V_BUS) == 0.0
    assert drive.max_drive_torque(no_load * 0.95, V_BUS) > 0.0
    assert drive.max_drive_torque(0.5 * no_load, V_BUS) > drive.max_drive_torque(
        0.97 * no_load, V_BUS)


def test_line_current_limit_caps_battery_current(params: ParamSet) -> None:
    params.set("motor.line_current_limit", 16.0)
    drive = ElectricDrive(params)
    for omega in (5.0, 20.0, 40.0):
        _run(drive, 500.0, omega)
        assert drive.bus_current <= 16.0 + 1e-6
    _run(drive, 500.0, 30.0)
    assert drive.bus_current == pytest.approx(16.0, rel=1e-3)


def test_power_balance_when_driving(drive: ElectricDrive) -> None:
    omega = 30.0
    _run(drive, 40.0, omega)
    electrical = drive.bus_current * V_BUS
    mechanical = drive.torque * omega
    expected = (mechanical + drive.copper_loss) / drive.controller_efficiency
    assert electrical == pytest.approx(expected + drive.standby_power, rel=1e-6)
    assert electrical > mechanical > 0.0
    assert 0.6 < drive.efficiency(40.0, omega) < 0.95


def test_regen_returns_less_than_the_mechanical_power(drive: ElectricDrive) -> None:
    omega = 40.0
    _run(drive, -30.0, omega)
    assert drive.torque < 0.0
    returned = -drive.bus_current * V_BUS
    assert 0.0 < returned < -drive.torque * omega


def test_regen_respects_charge_current_limit_and_fades_at_low_speed(
        params: ParamSet) -> None:
    params.set_display("motor.regen_line_current_limit", 10.0)
    drive = ElectricDrive(params)
    _run(drive, -500.0, 50.0)
    assert -drive.bus_current <= 10.0 + 1e-6
    crawl = 0.5 * drive.regen_fade_start / drive.wheel_radius
    _run(drive, -500.0, crawl)
    assert drive.torque == 0.0


def test_no_reverse_drive_from_a_braking_command(drive: ElectricDrive) -> None:
    _run(drive, -50.0, 0.0)
    assert drive.torque == 0.0
    _run(drive, -50.0, -5.0)
    assert drive.torque == 0.0


def test_bus_off_means_no_torque_and_no_current(drive: ElectricDrive) -> None:
    _run(drive, 40.0, 20.0, bus_on=False)
    assert drive.torque == 0.0 and drive.bus_current == 0.0


def test_drag_grows_with_speed(drive: ElectricDrive) -> None:
    _run(drive, 0.0, 10.0, seconds=0.01)
    slow = drive.drag_torque
    _run(drive, 0.0, 50.0, seconds=0.01)
    assert drive.drag_torque > slow > 0.0


def test_heats_up_and_derates(params: ParamSet) -> None:
    params.set("motor.line_current_limit", 150.0)
    params.set("motor.thermal_capacity", 200.0)  # small so the test is quick
    drive = ElectricDrive(params)
    _run(drive, 500.0, 5.0, seconds=30.0)
    assert drive.temperature > drive.derate_start
    assert 0.0 <= drive.derate < 1.0
    assert drive.torque < drive.kt * drive.peak_current
    assert drive.temperature < drive.max_temperature + 5.0


def test_steady_temperature_matches_loss_over_conductance(params: ParamSet) -> None:
    params.set("motor.thermal_capacity", 200.0)
    drive = ElectricDrive(params)
    omega = 20.0
    _run(drive, 20.0, omega, seconds=600.0)
    conductance = drive.thermal_conductance * (
        1.0 + drive.cooling_factor * omega * drive.wheel_radius)
    expected = AIR + (drive.copper_loss + drive.drag_power) / conductance
    assert drive.temperature == pytest.approx(expected, rel=1e-3)


def test_inconsistent_parameters_are_rejected(params: ParamSet) -> None:
    params.set_display("motor.max_temperature", 100.0)
    with pytest.raises(ValueError, match="max_temperature"):
        ElectricDrive(params)
