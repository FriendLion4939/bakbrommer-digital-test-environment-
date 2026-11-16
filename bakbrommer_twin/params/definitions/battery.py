"""Parameters: traction battery and BMS."""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Status

EST = Status.ESTIMATED


def register(reg: Registry) -> None:
    """Declare battery parameters."""
    reg.category("battery", "Battery")
    reg.integer("battery.cells_series", 17, 4, 30, "Cells in series",
                "Number of Li-polymer cells in series (17 cells = 71.4 V full).",
                Status.MEASURED)
    reg.number("battery.capacity", 30.0, "Ah", 1.0, 300.0, "Capacity",
               "Usable charge of the pack from full to empty.", EST)
    reg.curve("battery.ocv_soc", [0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100], "%", 0, 100,
              "Rest-voltage curve: state of charge",
              "State-of-charge points of the rest-voltage curve (rising).", EST)
    reg.curve("battery.ocv_cell_voltage",
              [3.30, 3.53, 3.62, 3.70, 3.75, 3.79, 3.83, 3.88, 3.94, 4.01, 4.10, 4.20],
              "V", 2.5, 4.4, "Rest-voltage curve: cell voltage",
              "Voltage of one resting cell at each state-of-charge point.", EST)
    reg.number("battery.internal_resistance", 60.0, "mΩ", 1.0, 2000.0, "Internal resistance",
               "Resistance of the whole pack including wiring at 25 °C. Causes the "
               "immediate voltage drop under load.", EST)
    reg.number("battery.polarisation_resistance", 30.0, "mΩ", 0.0, 1000.0,
               "Slow-sag resistance",
               "Extra resistance that builds up over the sag time during a long pull.", EST)
    reg.number("battery.polarisation_time", 20.0, "s", 1.0, 600.0, "Slow-sag time",
               "Time constant of the slow part of the voltage sag.", EST)
    reg.number("battery.cold_resistance_factor", 1.5, "%", 0.0, 10.0,
               "Resistance rise when cold",
               "Increase of the internal resistance per degree below 25 °C.", EST)
    reg.number("battery.bms_discharge_limit", 35.0, "A", 5.0, 400.0, "BMS discharge limit",
               "Largest current the BMS allows out of the pack (may become 150 A).", EST)
    reg.number("battery.bms_charge_limit", 15.0, "A", 0.0, 200.0, "BMS charge limit",
               "Largest current the BMS allows into the pack (regen).", EST)
    reg.flag("battery.bms_trip_enabled", True, "BMS cuts power on overcurrent",
             "When on, the simulated BMS disconnects the pack after an overcurrent, "
             "as the real one does. When off, overcurrent is only reported.")
    reg.number("battery.bms_trip_delay", 0.5, "s", 0.0, 30.0, "BMS trip delay",
               "How long the current may stay above the limit before the BMS trips.")
    reg.number("battery.bms_reset_time", 5.0, "s", 0.0, 120.0, "BMS reset time",
               "How long the pack stays disconnected after a trip.")
    reg.number("battery.min_voltage", 60.0, "V", 20.0, 100.0, "Minimum voltage",
               "Pack voltage below which an under-voltage event is reported.",
               Status.MEASURED)
    reg.number("battery.initial_soc", 90.0, "%", 1.0, 100.0, "State of charge at start",
               "State of charge at the beginning of a simulation.")
    reg.number("battery.thermal_capacity", 14000.0, "J/K", 500.0, 200000.0, "Thermal capacity",
               "Heat needed to warm the pack by one degree.", EST)
    reg.number("battery.thermal_conductance", 2.0, "W/K", 0.05, 50.0, "Cooling",
               "Heat the pack loses per degree above the air temperature.", EST)
    reg.number("battery.max_temperature", 60.0, "°C", 30.0, 90.0, "Maximum temperature",
               "Pack temperature above which an overheating event is reported.", EST)
    reg.number("battery.aux_power", 20.0, "W", 0.0, 500.0, "Auxiliary power",
               "Constant draw of lights, DC-DC converter and electronics.", EST)
