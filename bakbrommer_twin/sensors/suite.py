"""All sensors of the vehicle and their connection to the controller inputs.

``_GETTERS`` says which true quantity each sensor measures. The suite samples
each sensor at its own rate and copies the readings into
:class:`ControllerInputs`.

Assumptions (see docs/PHYSICS.md): the IMU sits at the centre of gravity and
is aligned with the body axes; the accelerometer measures specific force
(acceleration minus gravity), as a real MEMS sensor does.
"""

from __future__ import annotations

from collections.abc import Callable

from bakbrommer_twin.control.interface import ControllerInputs
from bakbrommer_twin.params.definitions.sensors import SENSOR_NAMES
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.inputs import RiderInputs
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.sensors.model import NoiseSource, Sensor

Getter = Callable[[], float]


def _getters(vehicle: Vehicle, rider: RiderInputs) -> dict[str, Getter]:
    """True value behind each sensor (SI units)."""
    chassis, wheels, battery = vehicle.chassis, vehicle.wheels, vehicle.battery
    return {
        "throttle": lambda: rider.throttle,
        "brake_front_pressure": lambda: vehicle.brakes.front_pressure,
        "brake_rear_pressure": lambda: vehicle.brakes.rear_pressure,
        "steering_angle": lambda: rider.steer,
        "engine_speed": lambda: vehicle.engine.speed,
        "vehicle_speed": lambda: chassis.u,
        "wheel_speed_fl": lambda: wheels[0].omega,
        "wheel_speed_fr": lambda: wheels[1].omega,
        "wheel_speed_r": lambda: wheels[2].omega,
        "accel_x": lambda: chassis.accel_x,
        "accel_y": lambda: chassis.accel_y,
        "accel_z": lambda: chassis.accel_z,
        "gyro_x": lambda: chassis.p,
        "gyro_y": lambda: chassis.q,
        "gyro_z": lambda: chassis.r,
        "battery_voltage": lambda: battery.voltage,
        "battery_current": lambda: battery.current,
        "motor_temp_l": lambda: vehicle.drive_left.temperature,
        "motor_temp_r": lambda: vehicle.drive_right.temperature,
    }


class SensorSuite:
    """Samples every sensor and fills the controller inputs."""

    def __init__(self, params: ParamSet, vehicle: Vehicle, rider: RiderInputs,
                 time_step: float) -> None:
        ideal = params.flag("sensors.ideal")
        noise_source = NoiseSource(params.integer("sim.random_seed"))
        getters = _getters(vehicle, rider)
        self.sensors: dict[str, Sensor] = {}
        self._schedule: list[tuple[Sensor, Getter]] = []
        # sensors grouped by sample period (in steps) so a step only visits those due
        self._by_period: dict[int, list[tuple[Sensor, Getter]]] = {}
        for name in SENSOR_NAMES:
            key = f"sensors.{name}"
            period = max(1, round(1.0 / (params.num(f"{key}.rate") * time_step)))
            delay = round(params.num(f"{key}.delay") / (period * time_step))
            noise = params.num(f"{key}.noise")
            bias = params.num(f"{key}.bias")
            resolution = params.num(f"{key}.resolution")
            if ideal:
                sensor = Sensor(0.0, 0.0, 0.0, 1, 0, noise_source)
            else:
                sensor = Sensor(noise, bias, resolution, period, delay, noise_source)
            self.sensors[name] = sensor
            self._schedule.append((sensor, getters[name]))
            self._by_period.setdefault(sensor.period_steps, []).append((sensor, getters[name]))
        self._rider = rider

    def preset(self) -> None:
        """Start every sensor at the present true value (no start-up transient)."""
        for sensor, getter in self._schedule:
            sensor.preset(getter())

    def sample(self, step_index: int) -> None:
        """Sample the sensors that are due at this simulation step."""
        for period, members in self._by_period.items():
            if step_index % period == 0:
                for sensor, getter in members:
                    sensor.sample(getter())

    def fill(self, inputs: ControllerInputs) -> None:
        """Copy the current readings into the controller inputs."""
        s = self.sensors
        inputs.throttle = s["throttle"].value
        inputs.brake_front_pressure = s["brake_front_pressure"].value
        inputs.brake_rear_pressure = s["brake_rear_pressure"].value
        inputs.steering_angle = s["steering_angle"].value
        inputs.engine_speed = s["engine_speed"].value
        inputs.vehicle_speed = s["vehicle_speed"].value
        inputs.wheel_speed_fl = s["wheel_speed_fl"].value
        inputs.wheel_speed_fr = s["wheel_speed_fr"].value
        inputs.wheel_speed_r = s["wheel_speed_r"].value
        inputs.accel_x = s["accel_x"].value
        inputs.accel_y = s["accel_y"].value
        inputs.accel_z = s["accel_z"].value
        inputs.gyro_x = s["gyro_x"].value
        inputs.gyro_y = s["gyro_y"].value
        inputs.gyro_z = s["gyro_z"].value
        inputs.battery_voltage = s["battery_voltage"].value
        inputs.battery_current = s["battery_current"].value
        inputs.motor_temp_l = s["motor_temp_l"].value
        inputs.motor_temp_r = s["motor_temp_r"].value
        inputs.mode_request = float(self._rider.mode_request)
