"""Parameters: electric hub motors with their Fardriver controllers.

Both front motors share one parameter set.
"""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Status

EST = Status.ESTIMATED


def register(reg: Registry) -> None:
    """Declare motor and motor-controller parameters."""
    reg.category("motor", "Electric motors")
    reg.number("motor.rated_power", 1300.0, "W", 100.0, 10000.0, "Rated power per motor",
               "Continuous power on the motor label (Bosch A4W1300).", Status.MEASURED)
    reg.number("motor.torque_constant", 0.87, "Nm/A", 0.05, 5.0, "Torque constant",
               "Wheel torque per ampere of phase current (peak value of the sine).", EST)
    reg.number("motor.phase_resistance", 45.0, "mΩ", 1.0, 1000.0, "Phase resistance at 20 °C",
               "Resistance of one motor phase (line-to-neutral) at 20 °C.", EST)
    reg.number("motor.peak_phase_current", 135.0, "A", 5.0, 450.0, "Peak phase current",
               "Phase current limit set in the Fardriver. Sets the peak torque.", EST)
    reg.number("motor.line_current_limit", 16.0, "A", 1.0, 200.0, "Line current limit",
               "Battery-side current limit set in each Fardriver. Two motors together must "
               "stay below the BMS limit, or the BMS cuts the power.", EST)
    reg.number("motor.regen_phase_current", 60.0, "A", 0.0, 450.0, "Regen phase current",
               "Phase current limit while braking electrically.", EST)
    reg.number("motor.regen_line_current_limit", 20.0, "A", 0.0, 200.0,
               "Regen line current limit",
               "Battery-side charging current limit per Fardriver while braking.", EST)
    reg.number("motor.regen_fade_start_speed", 2.0, "km/h", 0.0, 20.0, "Regen cut-off speed",
               "Below this wheel speed there is no electric braking.")
    reg.number("motor.regen_fade_end_speed", 6.0, "km/h", 0.5, 30.0, "Regen full-strength speed",
               "Above this wheel speed electric braking is at full strength.")
    reg.number("motor.modulation_limit", 0.55, "-", 0.3, 0.6, "Voltage use",
               "Largest phase voltage the controller can make, as a fraction of the "
               "battery voltage (0.577 is the theoretical limit).")
    reg.number("motor.field_weakening_ratio", 1.15, "-", 1.0, 2.5, "Field weakening ratio",
               "How far the top speed is stretched beyond the natural no-load speed.", EST)
    reg.number("motor.drag_torque_static", 0.4, "Nm", 0.0, 5.0, "Drag torque at standstill",
               "Torque needed to turn the unpowered motor slowly (bearings, cogging).", EST)
    reg.number("motor.drag_torque_speed", 0.010, "Nm·s/rad", 0.0, 0.2, "Drag torque growth",
               "Extra drag torque per rad/s of wheel speed (iron losses).", EST)
    reg.number("motor.controller_efficiency", 97.0, "%", 80.0, 100.0, "Controller efficiency",
               "Share of the electrical power that passes through the Fardriver.", EST)
    reg.number("motor.standby_power", 3.0, "W", 0.0, 50.0, "Controller standby power",
               "Power one Fardriver draws when switched on but idle.", EST)
    reg.number("motor.torque_response_time", 20.0, "ms", 1.0, 500.0, "Torque response time",
               "Time constant with which the motor torque follows the command.", EST)
    reg.number("motor.thermal_capacity", 4000.0, "J/K", 200.0, 50000.0, "Thermal capacity",
               "Heat needed to warm the motor by one degree.", EST)
    reg.number("motor.thermal_conductance", 3.0, "W/K", 0.2, 50.0, "Cooling at standstill",
               "Heat the standing motor loses per degree above the air temperature.", EST)
    reg.number("motor.cooling_speed_factor", 0.10, "s/m", 0.0, 2.0, "Cooling gain with speed",
               "Cooling = standstill cooling × (1 + factor × wheel rim speed in m/s).", EST)
    reg.number("motor.derate_start_temperature", 110.0, "°C", 40.0, 200.0, "Derating start",
               "Motor temperature above which torque is reduced.", EST)
    reg.number("motor.max_temperature", 140.0, "°C", 50.0, 220.0, "Maximum temperature",
               "Motor temperature at which torque is cut to zero.", EST)
