"""Battery: voltage sag, state of charge, heating, BMS."""

import pytest

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.physics.battery import Battery

DT = 0.001
AIR = 20.0


def _run(battery: Battery, current: float, seconds: float) -> None:
    for _ in range(round(seconds / DT)):
        battery.step(DT, current, AIR)


@pytest.fixture
def battery(params: ParamSet) -> Battery:
    params.set("battery.aux_power", 0.0)
    params.set("environment.air_temperature", 25.0)
    return Battery(params)


def test_rest_voltage_follows_cell_curve(params: ParamSet) -> None:
    params.set("battery.initial_soc", 1.0)
    assert Battery(params).open_circuit_voltage() == pytest.approx(17 * 4.20)
    params.set("battery.initial_soc", 0.5)
    assert Battery(params).open_circuit_voltage() == pytest.approx(17 * 3.83)


def test_immediate_sag_is_current_times_resistance(battery: Battery) -> None:
    rest = battery.open_circuit_voltage()
    battery.step(DT, 30.0, 25.0)
    assert rest - battery.voltage == pytest.approx(30.0 * battery.r0, rel=0.01)


def test_slow_sag_builds_up_to_polarisation_resistance(battery: Battery) -> None:
    _run(battery, 30.0, 5 * battery.tau)
    assert battery.polarisation == pytest.approx(30.0 * battery.r1, rel=0.01)


def test_coulomb_counting(battery: Battery) -> None:
    start = battery.soc
    _run(battery, 30.0, 60.0)
    assert start - battery.soc == pytest.approx(30.0 * 60.0 / battery.capacity, rel=1e-6)
    _run(battery, -10.0, 60.0)  # charging raises it again
    assert battery.soc > start - 30.0 * 60.0 / battery.capacity


def test_cold_pack_has_higher_resistance(params: ParamSet) -> None:
    params.set("environment.air_temperature", 25.0)
    warm = Battery(params).resistance()
    params.set("environment.air_temperature", 5.0)
    cold = Battery(params).resistance()
    assert cold == pytest.approx(warm * (1.0 + 20.0 * params.num(
        "battery.cold_resistance_factor")))


def test_heats_under_load(battery: Battery) -> None:
    start = battery.temperature
    _run(battery, 30.0, 120.0)
    assert battery.temperature > start
    assert battery.loss_power == pytest.approx(
        30.0**2 * battery.r0 + battery.polarisation**2 / battery.r1, rel=1e-6)


def test_bms_trips_after_delay_and_reconnects(battery: Battery) -> None:
    over = battery.discharge_limit + 5.0
    _run(battery, over, battery.trip_delay * 0.8)
    assert battery.connected
    _run(battery, over, battery.trip_delay * 0.4)
    assert not battery.connected and battery.tripped_count == 1
    assert battery.current == 0.0
    _run(battery, 0.0, battery.reset_time + 0.1)
    assert battery.connected


def test_short_overcurrent_does_not_trip(battery: Battery) -> None:
    for _ in range(5):
        _run(battery, battery.discharge_limit + 20.0, battery.trip_delay * 0.5)
        _run(battery, 10.0, 0.05)
    assert battery.connected and battery.tripped_count == 0


def test_charge_limit_trips_too(battery: Battery) -> None:
    _run(battery, -(battery.charge_limit + 5.0), battery.trip_delay * 1.2)
    assert not battery.connected


def test_trip_can_be_disabled(params: ParamSet) -> None:
    params.set("battery.bms_trip_enabled", False)
    battery = Battery(params)
    _run(battery, 200.0, 2.0)
    assert battery.connected


def test_aux_power_drains_the_pack(params: ParamSet) -> None:
    params.set("battery.aux_power", 66.0)
    battery = Battery(params)
    _run(battery, 0.0, 1.0)
    assert battery.current == pytest.approx(66.0 / battery.voltage, rel=0.01)
