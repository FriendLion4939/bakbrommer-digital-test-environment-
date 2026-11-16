"""The reference controller: one control period of the STM32G4 logic.

Order of one step (each block is its own file in this folder):

1. speed estimate from wheel speeds and accelerometer      (estimator.py)
2. ride mode settings, gliding between modes                (modes.py)
3. petrol engine start/stop                                 (engine_manager.py)
4. torque request: throttle map × mode torque × assist fade, or regen (regen.py)
5. rollover protection scales driving torque                (limits.py)
6. torque vectoring splits it left/right                    (vectoring.py)
7. traction control / regen anti-lock per wheel             (slip.py)
8. battery current, voltage and temperature limits          (limits.py)
9. torque rate limit

Blending rule (step 4): the motors deliver ``electric_torque × throttle^exponent``.
While the petrol engine runs, this assist fades out linearly between the
mode's fade speeds (the engine is more efficient at speed); while the engine
is off the motors keep full authority.
"""

from __future__ import annotations

from bakbrommer_twin.control.interface import ControllerInputs, ControllerOutputs
from bakbrommer_twin.control.reference.engine_manager import CRANKING, EngineManager
from bakbrommer_twin.control.reference.estimator import SpeedEstimator
from bakbrommer_twin.control.reference.limits import PowerLimiter, StabilityLimiter
from bakbrommer_twin.control.reference.modes import ModeManager
from bakbrommer_twin.control.reference.regen import Regen
from bakbrommer_twin.control.reference.slip import SlipLimiter
from bakbrommer_twin.control.reference.vectoring import TorqueVectoring
from bakbrommer_twin.params.paramset import ParamSet


class ReferenceController:
    """Hybrid drive controller with ride modes, TC, vectoring, regen and limits."""

    def __init__(self, params: ParamSet) -> None:
        self.estimator = SpeedEstimator(params)
        self.modes = ModeManager(params)
        self.engine = EngineManager(params)
        self.regen = Regen(params)
        self.vectoring = TorqueVectoring(params)
        self.stability = StabilityLimiter(params)
        self.power = PowerLimiter(params)
        self.traction_enabled = params.flag("control.traction.enabled")
        slip_target = params.num("control.traction.slip_target")
        self.traction_left = SlipLimiter(params, slip_target)
        self.traction_right = SlipLimiter(params, slip_target)
        regen_slip = params.num("control.regen.slip_limit")
        self.antilock_left = SlipLimiter(params, regen_slip)
        self.antilock_right = SlipLimiter(params, regen_slip)
        self.throttle_deadband = params.num("control.regen.throttle_deadband")
        self.rate_limit = params.num("control.torque_rate_limit")
        self.filter_time = params.num("control.vectoring.filter_time")
        self.front_radius = params.num("wheels.front_radius")
        self.lateral_accel = 0.0  # low-pass filtered accelerometer Y, m/s²
        self.torque_left = 0.0  # last commands, Nm
        self.torque_right = 0.0

    def reset(self) -> None:
        """Return every block to its power-on state."""
        self.estimator.reset()
        self.modes.reset()
        self.engine.reset()
        self.stability.reset()
        self.power.reset()
        for limiter in (self.traction_left, self.traction_right, self.antilock_left,
                        self.antilock_right):
            limiter.reset()
        self.lateral_accel = self.torque_left = self.torque_right = 0.0

    def step(self, inputs: ControllerInputs, outputs: ControllerOutputs) -> None:
        """Run one control period."""
        dt = inputs.dt
        throttle = min(1.0, max(0.0, inputs.throttle))
        threshold = self.regen.brake_threshold
        braking = (inputs.brake_front_pressure > threshold
                   or inputs.brake_rear_pressure > threshold)
        driving = throttle > self.throttle_deadband and not braking

        # 1–3: speed, mode, engine
        speed = self.estimator.step(inputs, driving)
        mode = self.modes.step(dt, inputs.mode_request)
        engine = self.engine
        engine.step(dt, mode, speed, inputs.engine_speed)
        self.lateral_accel += (inputs.accel_y - self.lateral_accel) * min(
            1.0, dt / self.filter_time)

        # 4: torque request per motor (positive = drive, negative = regen)
        regen_torque = 0.0
        if driving:
            torque = mode.electric_torque * throttle**mode.throttle_exponent
            if engine.running:  # the engine helps: fade the assist out with speed
                fade = (mode.electric_fade_end - speed) / (
                    mode.electric_fade_end - mode.electric_fade_start)
                torque *= 0.0 if fade < 0.0 else (1.0 if fade > 1.0 else fade)
            # 5: rollover protection
            torque *= self.stability.step(dt, self.lateral_accel, inputs.gyro_x)
        else:
            regen_torque = self.regen.step(mode, throttle, inputs.brake_front_pressure, speed,
                                           inputs.battery_voltage)
            torque = -regen_torque
            self.stability.step(dt, self.lateral_accel, inputs.gyro_x)

        # 6: left/right split
        vectoring = self.vectoring
        vectoring.step(torque, speed, inputs.steering_angle, inputs.gyro_z, self.lateral_accel)
        left, right = vectoring.left, vectoring.right

        # 7: wheel slip limits (always updated so they recover when not needed)
        estimator = self.estimator
        spin_left = self.traction_left.step(dt, estimator.left, speed, 1.0)
        spin_right = self.traction_right.step(dt, estimator.right, speed, 1.0)
        lock_left = self.antilock_left.step(dt, estimator.left, speed, -1.0)
        lock_right = self.antilock_right.step(dt, estimator.right, speed, -1.0)
        if not self.traction_enabled:
            spin_left = spin_right = 0.0
        left *= 1.0 - (spin_left if left > 0.0 else lock_left)
        right *= 1.0 - (spin_right if right > 0.0 else lock_right)

        # 8: battery and temperature limits on the mechanical power requested
        power = (left * inputs.wheel_speed_fl + right * inputs.wheel_speed_fr)
        factor = self.power.step(
            dt, left + right >= 0.0, power, mode.current_limit_share, inputs.battery_voltage,
            inputs.battery_current, max(inputs.motor_temp_l, inputs.motor_temp_r))
        left *= factor
        right *= factor

        # 9: rate limit
        step = self.rate_limit * dt
        self.torque_left += min(step, max(-step, left - self.torque_left))
        self.torque_right += min(step, max(-step, right - self.torque_right))

        outputs.torque_left = self.torque_left
        outputs.torque_right = self.torque_right
        running = engine.running
        outputs.engine_throttle = mode.engine_throttle_gain * throttle if running else 0.0
        if engine.state == CRANKING:
            outputs.engine_throttle = 0.0
        outputs.engine_ignition = 1.0 if engine.ignition else 0.0
        outputs.engine_starter = 1.0 if engine.starter else 0.0
        outputs.active_mode = float(self.modes.active)
        outputs.diag_speed_estimate = speed
        outputs.diag_traction_left = spin_left if left >= 0.0 else lock_left
        outputs.diag_traction_right = spin_right if right >= 0.0 else lock_right
        outputs.diag_vectoring_torque = 0.5 * (vectoring.right - vectoring.left)
        outputs.diag_regen_torque = regen_torque
        outputs.diag_power_limit = factor
        outputs.diag_stability_limit = self.stability.factor
