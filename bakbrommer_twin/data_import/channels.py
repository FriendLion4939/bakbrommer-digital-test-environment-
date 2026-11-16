"""The channels a ride log can contain ("canonical" log channels).

They are the vehicle's sensors (same names as in ``params/definitions/sensors.py``)
plus the ride mode switch. A column of a CSV file or a CAN signal is mapped to
one of these names; replay and calibration then know what it means.

Each channel has a plausible range. Samples outside it are treated as bad
data (sensor glitch, wrong unit in the mapping).
"""

from __future__ import annotations

from dataclasses import dataclass

from bakbrommer_twin.params import units
from bakbrommer_twin.params.definitions.control import RIDE_MODES
from bakbrommer_twin.params.definitions.sensors import SENSOR_SPECS

# Plausible range of each channel in its friendly unit: (low, high).
_RANGES: dict[str, tuple[float, float]] = {
    "throttle": (-5.0, 105.0),
    "brake_front_pressure": (-5.0, 250.0),
    "brake_rear_pressure": (-5.0, 250.0),
    "steering_angle": (-90.0, 90.0),
    "engine_speed": (0.0, 15000.0),
    "vehicle_speed": (-20.0, 200.0),
    "wheel_speed_fl": (-300.0, 3000.0),
    "wheel_speed_fr": (-300.0, 3000.0),
    "wheel_speed_r": (-300.0, 3000.0),
    "accel_x": (-40.0, 40.0),
    "accel_y": (-40.0, 40.0),
    "accel_z": (-40.0, 40.0),
    "gyro_x": (-600.0, 600.0),
    "gyro_y": (-600.0, 600.0),
    "gyro_z": (-600.0, 600.0),
    "battery_voltage": (20.0, 120.0),
    "battery_current": (-300.0, 500.0),
    "motor_temp_l": (-40.0, 250.0),
    "motor_temp_r": (-40.0, 250.0),
}
MODE_CHANNEL = "ride_mode"


@dataclass(frozen=True)
class LogChannel:
    """One canonical log channel."""

    name: str
    title: str
    unit: str  # usual friendly unit (the mapping may give another compatible one)
    low: float  # plausible range, SI
    high: float
    sim_channel: str  # channel of a simulation result it is compared with


def _build() -> dict[str, LogChannel]:
    channels = {}
    for spec in SENSOR_SPECS:
        low, high = _RANGES[spec.name]
        channels[spec.name] = LogChannel(spec.name, spec.title, spec.unit,
                                         units.to_si(low, spec.unit),
                                         units.to_si(high, spec.unit), f"sens_{spec.name}")
    channels[MODE_CHANNEL] = LogChannel(MODE_CHANNEL, "Ride mode switch", "-", 0.0,
                                        float(len(RIDE_MODES) - 1), "mode_request")
    return channels


LOG_CHANNELS: dict[str, LogChannel] = _build()
# Channels a replay needs to drive the simulated vehicle.
REPLAY_INPUTS: tuple[str, ...] = ("throttle", "brake_front_pressure", "steering_angle")
