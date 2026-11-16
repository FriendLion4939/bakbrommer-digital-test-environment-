"""The boundary between the simulated vehicle and the controller ("brain").

A controller sees only :class:`ControllerInputs` (what the STM32G4 gets from
its sensors and switches) and fills in :class:`ControllerOutputs` (what it
commands). Every field is a plain number in SI units, so the two records map
one-to-one onto two C structs of ``double`` — that is how real STM32 C code is
plugged in later (software-in-the-loop, see ``control/sil``). The C header is
generated from these two classes; keep them flat and numeric.

To add a signal: add a field here (with unit and meaning in the comment),
fill it in ``sensors/suite.py`` (inputs) or use it in ``sim/simulator.py``
(outputs), and regenerate the SIL header.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class ControllerInputs:
    """Sensor readings and switch positions, as the controller sees them."""

    time: float = 0.0  # s since start
    dt: float = 0.0  # s since the previous controller step
    throttle: float = 0.0  # twist grip position, 0…1
    brake_front_pressure: float = 0.0  # Pa
    brake_rear_pressure: float = 0.0  # Pa
    steering_angle: float = 0.0  # handlebar angle, rad (+ = left)
    engine_speed: float = 0.0  # rad/s
    vehicle_speed: float = 0.0  # m/s
    wheel_speed_fl: float = 0.0  # rad/s
    wheel_speed_fr: float = 0.0  # rad/s
    wheel_speed_r: float = 0.0  # rad/s
    accel_x: float = 0.0  # m/s², forward (specific force, includes gravity)
    accel_y: float = 0.0  # m/s², left
    accel_z: float = 0.0  # m/s², up
    gyro_x: float = 0.0  # rad/s, roll rate
    gyro_y: float = 0.0  # rad/s, pitch rate
    gyro_z: float = 0.0  # rad/s, yaw rate
    battery_voltage: float = 0.0  # V
    battery_current: float = 0.0  # A (+ = discharging)
    motor_temp_l: float = 0.0  # °C
    motor_temp_r: float = 0.0  # °C
    mode_request: float = 0.0  # ride mode switch position (index into RIDE_MODES)


@dataclass(slots=True)
class ControllerOutputs:
    """Actuator commands plus diagnostic values for the charts."""

    torque_left: float = 0.0  # Nm at the left front wheel (+ drive, − regen)
    torque_right: float = 0.0  # Nm at the right front wheel
    engine_throttle: float = 0.0  # 0…1, used only with throttle-by-wire
    engine_ignition: float = 1.0  # 1 = petrol engine may run, 0 = cut
    engine_starter: float = 0.0  # 1 = crank the petrol engine
    active_mode: float = 0.0  # ride mode in effect (index into RIDE_MODES)
    # diagnostics (not used by the vehicle model)
    diag_speed_estimate: float = 0.0  # m/s, controller's own speed estimate
    diag_traction_left: float = 0.0  # 0…1, share of torque removed by traction control
    diag_traction_right: float = 0.0  # 0…1
    diag_vectoring_torque: float = 0.0  # Nm moved from the left to the right wheel
    diag_regen_torque: float = 0.0  # Nm of electric braking requested per wheel
    diag_power_limit: float = 1.0  # 0…1, torque factor from battery/thermal limits
    diag_stability_limit: float = 1.0  # 0…1, torque factor from rollover protection


class Controller(Protocol):
    """What every controller implementation provides."""

    def reset(self) -> None:
        """Return to the power-on state."""

    def step(self, inputs: ControllerInputs, outputs: ControllerOutputs) -> None:
        """Read ``inputs`` and overwrite ``outputs`` for this control period."""
