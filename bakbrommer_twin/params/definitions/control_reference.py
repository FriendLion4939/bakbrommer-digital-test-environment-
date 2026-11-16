"""Parameters: tuning of the reference controller (the STM32G4 logic in Python).

Per-mode settings are generated from ``_MODE_DEFAULTS``. To add a ride mode:
add its name to ``RIDE_MODES`` in ``control.py`` and a column here.
"""

from __future__ import annotations

from bakbrommer_twin.params.definitions.control import RIDE_MODES
from bakbrommer_twin.params.registry import Registry

# (key, unit, low, high, label, description, values for normal / eco / sport / standalone)
_MODE_NUMBERS: tuple[tuple[str, str, float, float, str, str, tuple[float, ...]], ...] = (
    ("electric_torque", "Nm", 0.0, 200.0, "electric torque at full throttle",
     "Torque command per front motor at full throttle.", (45.0, 30.0, 80.0, 115.0)),
    ("throttle_exponent", "-", 0.3, 3.0, "throttle curve",
     "Shape of the throttle response: 1 = linear, above 1 = gentle at small openings, "
     "below 1 = eager.", (1.0, 1.5, 0.8, 1.0)),
    ("electric_fade_start", "km/h", 0.0, 300.0, "electric assist fades from",
     "Above this speed the electric assist is reduced while the petrol engine runs.",
     (45.0, 25.0, 300.0, 300.0)),
    ("electric_fade_end", "km/h", 1.0, 400.0, "electric assist ends at",
     "At this speed the electric assist has faded to zero while the petrol engine runs.",
     (60.0, 40.0, 400.0, 400.0)),
    ("coast_regen_torque", "Nm", 0.0, 100.0, "regen with closed throttle",
     "Electric braking torque per motor when the throttle is closed.", (4.0, 8.0, 0.0, 6.0)),
    ("brake_regen_torque", "Nm", 0.0, 150.0, "regen at full brake",
     "Extra electric braking torque per motor at full front brake pressure.",
     (30.0, 30.0, 20.0, 40.0)),
    ("engine_start_speed", "km/h", 0.0, 100.0, "petrol engine joins above",
     "With automatic start/stop: below this speed the vehicle drives electrically and "
     "the petrol engine is off.", (0.0, 15.0, 0.0, 0.0)),
    ("engine_throttle_gain", "-", 0.0, 1.0, "petrol throttle share",
     "Throttle-by-wire only: petrol throttle = this share of the rider's throttle.",
     (1.0, 0.8, 1.0, 0.0)),
    ("current_limit_share", "%", 5.0, 100.0, "share of the battery current limit",
     "How much of the controller's battery current limit this mode may use.",
     (90.0, 70.0, 100.0, 100.0)),
)
# Is the petrol engine used in each mode? (normal / eco / sport / standalone)
_MODE_ENGINE = (True, True, True, False)


def register(reg: Registry) -> None:
    """Declare the reference controller's tuning parameters."""
    _modes(reg)
    _engine_management(reg)
    _estimator_and_limits(reg)
    _traction_and_vectoring(reg)
    _regen_and_stability(reg)


def _modes(reg: Registry) -> None:
    for index, mode in enumerate(RIDE_MODES):
        title = mode.replace("_", " ").capitalize()
        for key, unit, low, high, label, description, values in _MODE_NUMBERS:
            reg.number(f"control.mode_{mode}.{key}", values[index], unit, low, high,
                       f"{title}: {label}", description)
        reg.flag(f"control.mode_{mode}.engine_enabled", _MODE_ENGINE[index],
                 f"{title}: petrol engine used",
                 "Off: this mode drives on the electric motors alone and keeps the "
                 "petrol engine switched off.")
    reg.number("control.mode_blend_time", 0.8, "s", 0.0, 10.0, "Mode change blend time",
               "Time over which the settings glide from the old ride mode to the new one.")
    reg.number("control.torque_rate_limit", 400.0, "Nm/s", 10.0, 10000.0, "Torque rate limit",
               "Fastest change of the motor torque command.")


def _engine_management(reg: Registry) -> None:
    reg.flag("control.engine_auto_start_stop", True, "Automatic engine start/stop",
             "On: the controller cranks and stops the petrol engine as the ride mode needs. "
             "Off: the rider starts it; the controller only cuts the ignition in "
             "electric-only modes.")
    reg.number("control.engine_running_speed", 1000.0, "rpm", 300.0, 3000.0,
               "Engine counts as running above",
               "Engine speed above which the controller releases the starter.")
    reg.number("control.engine_crank_timeout", 3.0, "s", 0.5, 20.0, "Longest cranking time",
               "If the engine has not started after this time the starter rests.")
    reg.number("control.engine_crank_pause", 2.0, "s", 0.1, 30.0, "Pause between start attempts",
               "Rest time of the starter after a failed attempt.")
    reg.number("control.engine_stop_delay", 3.0, "s", 0.0, 60.0, "Engine stop delay",
               "The engine is only switched off after it has been unwanted for this long.")
    reg.number("control.engine_speed_hysteresis", 4.0, "km/h", 0.0, 30.0,
               "Engine start/stop speed gap",
               "The engine is stopped again only this far below its start speed.")


def _estimator_and_limits(reg: Registry) -> None:
    reg.number("control.estimator_accel_margin", 2.0, "m/s²", 0.1, 20.0,
               "Speed estimate: trust in the accelerometer",
               "The speed estimate may change this much faster or slower than the "
               "accelerometer says. Smaller = spinning wheels are ignored better.")
    reg.flag("control.estimator_use_speed_sensor", True, "Speed estimate uses the speed sensor",
             "On: the vehicle speed sensor is used together with the wheel speeds.")
    reg.number("control.limits.battery_current", 32.0, "A", 5.0, 400.0,
               "Battery current limit of the controller",
               "The controller keeps the battery current below this. Set it a little "
               "below the BMS discharge limit.")
    reg.number("control.limits.charge_current", 12.0, "A", 0.0, 200.0,
               "Charge current limit of the controller",
               "The controller keeps the regen current below this. Set it a little below "
               "the BMS charge limit.")
    reg.number("control.limits.assumed_efficiency", 80.0, "%", 40.0, 100.0,
               "Assumed drive efficiency",
               "Used to predict the battery current a torque request will need.")
    reg.number("control.limits.current_gain", 4.0, "1/s", 0.0, 100.0, "Current limit correction",
               "How quickly the torque is trimmed when the measured current is too high.")
    reg.number("control.limits.low_voltage_start", 62.0, "V", 20.0, 100.0,
               "Low-voltage power reduction starts",
               "Below this battery voltage the drive torque is reduced.")
    reg.number("control.limits.low_voltage_end", 60.0, "V", 20.0, 100.0,
               "Low-voltage power reduction complete",
               "At this battery voltage the drive torque is zero.")
    reg.number("control.limits.motor_temp_start", 100.0, "°C", 30.0, 200.0,
               "Motor temperature reduction starts",
               "Above this motor temperature the controller reduces the torque.")
    reg.number("control.limits.motor_temp_end", 130.0, "°C", 40.0, 220.0,
               "Motor temperature reduction complete",
               "At this motor temperature the controller commands no torque.")


def _traction_and_vectoring(reg: Registry) -> None:
    reg.flag("control.traction.enabled", True, "Traction control",
             "Reduces the torque of a front wheel that spins faster than the vehicle moves.")
    reg.number("control.traction.slip_target", 12.0, "%", 2.0, 60.0, "Traction: allowed slip",
               "Wheel slip above this is reduced.")
    reg.number("control.traction.min_speed", 1.5, "m/s", 0.2, 10.0,
               "Traction: reference speed floor",
               "Slip is calculated against at least this speed (avoids division by zero).")
    reg.number("control.traction.proportional_gain", 3.0, "-", 0.0, 50.0,
               "Traction: immediate cut",
               "Share of torque removed at once per unit of excess slip.")
    reg.number("control.traction.integral_gain", 30.0, "1/s", 0.0, 500.0,
               "Traction: growing cut",
               "How fast the torque cut grows while the slip stays too high.")
    reg.number("control.traction.recovery_rate", 2.0, "1/s", 0.05, 50.0, "Traction: recovery",
               "How fast the torque returns once the wheel grips again (1/s = full "
               "torque back in one second).")
    reg.flag("control.vectoring.enabled", True, "Torque vectoring",
             "Sends more torque to the outer (loaded) front wheel in a corner and corrects "
             "the yaw rate.")
    reg.number("control.vectoring.load_split_gain", 3.0, "-", 0.0, 10.0,
               "Vectoring: shift per g of cornering",
               "Share of torque moved from the inner to the outer wheel per g of sideways "
               "acceleration (1/gain = the g at which the inner wheel gets nothing).")
    reg.number("control.vectoring.yaw_gain", 40.0, "Nm·s/rad", 0.0, 500.0,
               "Vectoring: yaw rate correction",
               "Torque difference per rad/s of yaw rate error.")
    reg.number("control.vectoring.max_torque_difference", 40.0, "Nm", 0.0, 200.0,
               "Vectoring: largest yaw correction",
               "Limit of the torque difference from the yaw rate correction.")
    reg.number("control.vectoring.understeer_gradient", 0.002, "s²/m²", 0.0, 0.05,
               "Vectoring: understeer of the reference",
               "How much less the reference vehicle turns as speed rises.")
    reg.number("control.vectoring.max_lateral_accel", 4.0, "m/s²", 0.5, 12.0,
               "Vectoring: reference cornering limit",
               "The yaw rate reference never asks for more cornering than this.")
    reg.number("control.vectoring.filter_time", 50.0, "ms", 1.0, 1000.0,
               "Vectoring: accelerometer smoothing",
               "Time constant of the low-pass filter on the sideways acceleration.")


def _regen_and_stability(reg: Registry) -> None:
    reg.number("control.regen.throttle_deadband", 2.0, "%", 0.0, 20.0,
               "Regen: closed-throttle threshold",
               "Below this throttle opening the throttle counts as closed.")
    reg.number("control.regen.brake_threshold", 1.5, "bar", 0.0, 20.0,
               "Regen: brake detection threshold",
               "Brake pressure above which the rider counts as braking. Must be above "
               "the noise of the pressure sensor.")
    reg.number("control.regen.full_pressure", 30.0, "bar", 1.0, 200.0,
               "Regen: brake pressure for full regen",
               "Front brake pressure at which the brake regen reaches its full value.")
    reg.number("control.regen.fade_start_speed", 4.0, "km/h", 0.0, 30.0, "Regen: off below",
               "Below this speed the controller asks for no electric braking.")
    reg.number("control.regen.fade_end_speed", 10.0, "km/h", 1.0, 50.0, "Regen: full above",
               "Above this speed electric braking is at full strength.")
    reg.number("control.regen.voltage_start", 70.0, "V", 20.0, 120.0,
               "Regen: reduce above battery voltage",
               "Above this battery voltage (nearly full) regen is reduced.")
    reg.number("control.regen.voltage_end", 71.4, "V", 20.0, 120.0,
               "Regen: none above battery voltage",
               "At this battery voltage there is no regen (battery full).")
    reg.number("control.regen.slip_limit", 15.0, "%", 2.0, 80.0, "Regen: wheel slip limit",
               "Electric braking of a wheel is released when it turns this much slower "
               "than the vehicle moves (anti-lock for regen).")
    reg.flag("control.stability.enabled", True, "Rollover protection",
             "Reduces drive torque when cornering close to the wheel-lift limit.")
    reg.number("control.stability.accel_start", 2.2, "m/s²", 0.3, 12.0,
               "Rollover protection: starts at",
               "Sideways acceleration above which drive torque is reduced.")
    reg.number("control.stability.accel_end", 3.2, "m/s²", 0.5, 15.0,
               "Rollover protection: full at",
               "Sideways acceleration at which drive torque is at its smallest factor.")
    reg.number("control.stability.min_torque_factor", 20.0, "%", 0.0, 100.0,
               "Rollover protection: smallest torque",
               "Share of the drive torque that remains at full intervention.")
    reg.number("control.stability.roll_rate_limit", 20.0, "deg/s", 2.0, 200.0,
               "Rollover protection: roll rate trigger",
               "A roll rate above this (the vehicle is tipping) triggers full intervention.")
    reg.number("control.stability.hold_time", 0.5, "s", 0.0, 5.0,
               "Rollover protection: hold time",
               "Full intervention is held this long after a roll rate trigger.")
