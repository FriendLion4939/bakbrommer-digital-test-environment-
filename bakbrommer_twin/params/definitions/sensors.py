"""Parameters: sensor imperfections.

Every sensor gets the same five settings: noise, bias, delay, resolution and
sample rate. To add a sensor: add a line to ``SENSOR_SPECS`` here, a getter in
``sensors/suite.py`` and (if the controller needs it) a field in
``control/interface.py``.
"""

from __future__ import annotations

from typing import NamedTuple

from bakbrommer_twin.params.registry import Registry


class SensorSpec(NamedTuple):
    """Defaults of one sensor, in its friendly unit."""

    name: str
    title: str
    unit: str
    noise: float  # standard deviation
    resolution: float  # smallest step the sensor can report
    rate_hz: float
    delay_ms: float
    limit: float  # largest value allowed for noise/bias/resolution settings


SENSOR_SPECS: tuple[SensorSpec, ...] = (
    SensorSpec("throttle", "Throttle position", "%", 0.3, 0.025, 200.0, 2.0, 50.0),
    SensorSpec("brake_front_pressure", "Front brake pressure", "bar", 0.2, 0.05, 200.0, 2.0,
               50.0),
    SensorSpec("brake_rear_pressure", "Rear brake pressure", "bar", 0.2, 0.05, 200.0, 2.0, 50.0),
    SensorSpec("steering_angle", "Steering angle", "deg", 0.1, 0.088, 200.0, 2.0, 45.0),
    SensorSpec("engine_speed", "Engine speed", "rpm", 20.0, 10.0, 100.0, 10.0, 2000.0),
    SensorSpec("vehicle_speed", "Vehicle speed", "km/h", 0.2, 0.1, 50.0, 20.0, 30.0),
    SensorSpec("wheel_speed_fl", "Front-left wheel speed", "rpm", 1.0, 0.5, 200.0, 5.0, 300.0),
    SensorSpec("wheel_speed_fr", "Front-right wheel speed", "rpm", 1.0, 0.5, 200.0, 5.0, 300.0),
    SensorSpec("wheel_speed_r", "Rear wheel speed", "rpm", 1.0, 0.5, 200.0, 5.0, 300.0),
    SensorSpec("accel_x", "Accelerometer X (forward)", "m/s²", 0.08, 0.0024, 1000.0, 2.0, 20.0),
    SensorSpec("accel_y", "Accelerometer Y (left)", "m/s²", 0.08, 0.0024, 1000.0, 2.0, 20.0),
    SensorSpec("accel_z", "Accelerometer Z (up)", "m/s²", 0.08, 0.0024, 1000.0, 2.0, 20.0),
    SensorSpec("gyro_x", "Gyroscope X (roll rate)", "deg/s", 0.1, 0.0153, 1000.0, 2.0, 100.0),
    SensorSpec("gyro_y", "Gyroscope Y (pitch rate)", "deg/s", 0.1, 0.0153, 1000.0, 2.0, 100.0),
    SensorSpec("gyro_z", "Gyroscope Z (yaw rate)", "deg/s", 0.1, 0.0153, 1000.0, 2.0, 100.0),
    SensorSpec("battery_voltage", "Battery voltage", "V", 0.05, 0.1, 100.0, 10.0, 20.0),
    SensorSpec("battery_current", "Battery current", "A", 0.3, 0.1, 100.0, 10.0, 50.0),
    SensorSpec("motor_temp_l", "Left motor temperature", "°C", 0.5, 1.0, 10.0, 100.0, 30.0),
    SensorSpec("motor_temp_r", "Right motor temperature", "°C", 0.5, 1.0, 10.0, 100.0, 30.0),
)
SENSOR_NAMES: tuple[str, ...] = tuple(spec.name for spec in SENSOR_SPECS)


def register(reg: Registry) -> None:
    """Declare five parameters per sensor plus the master switch."""
    reg.category("sensors", "Sensors")
    reg.flag("sensors.ideal", False, "Ideal sensors",
             "On: all sensors are perfect (no noise, bias, delay or rounding). "
             "Useful to separate controller problems from sensor problems.")
    for spec in SENSOR_SPECS:
        key = f"sensors.{spec.name}"
        reg.number(f"{key}.noise", spec.noise, spec.unit, 0.0, spec.limit,
                   f"{spec.title}: noise",
                   "Random error added to every sample (standard deviation).")
        reg.number(f"{key}.bias", 0.0, spec.unit, -spec.limit, spec.limit,
                   f"{spec.title}: bias", "Constant error added to every sample.")
        reg.number(f"{key}.resolution", spec.resolution, spec.unit, 0.0, spec.limit,
                   f"{spec.title}: resolution",
                   "Smallest change the sensor can report (0 = infinitely fine).")
        reg.number(f"{key}.rate", spec.rate_hz, "Hz", 1.0, 10000.0,
                   f"{spec.title}: sample rate", "How often the sensor delivers a new value.")
        reg.number(f"{key}.delay", spec.delay_ms, "ms", 0.0, 1000.0,
                   f"{spec.title}: delay", "Age of the value when the controller sees it.")
