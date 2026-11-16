"""Sensor model: noise, bias, resolution, rate and delay."""

import numpy as np
import pytest
from helpers import Rig

from bakbrommer_twin.control.interface import ControllerInputs
from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.params.definitions.sensors import SENSOR_NAMES
from bakbrommer_twin.sensors.model import NoiseSource, Sensor
from bakbrommer_twin.sensors.suite import SensorSuite


def test_noise_has_requested_standard_deviation_and_bias() -> None:
    sensor = Sensor(noise=0.5, bias=2.0, resolution=0.0, period_steps=1, delay_samples=0,
                    noise_source=NoiseSource(7))
    readings = []
    for _ in range(20000):
        sensor.sample(10.0)
        readings.append(sensor.value)
    assert np.mean(readings) == pytest.approx(12.0, abs=0.02)
    assert np.std(readings) == pytest.approx(0.5, rel=0.03)


def test_resolution_rounds_to_steps() -> None:
    sensor = Sensor(0.0, 0.0, 0.25, 1, 0, NoiseSource(1))
    for true, expected in [(1.10, 1.0), (1.13, 1.25), (-0.40, -0.5), (0.0, 0.0)]:
        sensor.sample(true)
        assert sensor.value == pytest.approx(expected)


def test_delay_releases_old_samples() -> None:
    sensor = Sensor(0.0, 0.0, 0.0, 1, 3, NoiseSource(1))
    sensor.preset(0.0)
    outputs = []
    for value in range(1, 8):
        sensor.sample(float(value))
        outputs.append(sensor.value)
    assert outputs == [0.0, 0.0, 0.0, 1.0, 2.0, 3.0, 4.0]


def test_same_seed_same_noise() -> None:
    a, b, c = NoiseSource(3), NoiseSource(3), NoiseSource(4)
    first = [a.draw() for _ in range(5)]
    assert first == [b.draw() for _ in range(5)]
    assert first != [c.draw() for _ in range(5)]


def test_suite_samples_each_sensor_at_its_rate(params: ParamSet) -> None:
    rig = Rig(params, speed=10.0)
    suite = SensorSuite(params, rig.vehicle, rig.rider, rig.dt)
    suite.preset()
    assert set(suite.sensors) == set(SENSOR_NAMES)
    assert suite.sensors["accel_x"].period_steps == 1  # 1000 Hz at a 1 ms step
    assert suite.sensors["vehicle_speed"].period_steps == 20  # 50 Hz
    before = suite.sensors["vehicle_speed"].value
    rig.vehicle.chassis.u = 20.0
    suite.sample(1)  # not due
    assert suite.sensors["vehicle_speed"].value == before
    for step in (20, 40):  # due; the 20 ms delay is one sample
        suite.sample(step)
    assert suite.sensors["vehicle_speed"].value == pytest.approx(20.0, abs=1.0)


def test_ideal_sensors_report_the_truth(quiet: ParamSet) -> None:
    rig = Rig(quiet, speed=10.0)
    rig.rider.throttle = 0.37
    rig.run(0.5)
    suite = SensorSuite(quiet, rig.vehicle, rig.rider, rig.dt)
    suite.sample(0)
    inputs = ControllerInputs()
    suite.fill(inputs)
    vehicle = rig.vehicle
    assert inputs.throttle == 0.37
    assert inputs.vehicle_speed == vehicle.chassis.u
    assert inputs.wheel_speed_r == vehicle.wheels[2].omega
    assert inputs.battery_voltage == vehicle.battery.voltage
    assert inputs.engine_speed == vehicle.engine.speed


def test_accelerometer_measures_specific_force(quiet: ParamSet) -> None:
    rig = Rig(quiet)
    rig.run(2.0)  # at rest on level ground: feels +1 g upwards, nothing else
    chassis = rig.vehicle.chassis
    assert chassis.accel_z == pytest.approx(9.80665, rel=1e-3)
    assert chassis.accel_x == pytest.approx(0.0, abs=1e-3)
    rig.set_grade(10.0)
    rig.rider.brake_front = rig.rider.brake_rear = 1.0
    rig.run(3.0)  # parked nose-up on a slope: the brakes push forwards along the road
    # (2 % tolerance: the body also pitches a little on its springs)
    assert chassis.accel_x == pytest.approx(9.80665 * rig.env.grade_sin, rel=0.02)
