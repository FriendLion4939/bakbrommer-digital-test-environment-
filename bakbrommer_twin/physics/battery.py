"""Traction battery with BMS.

Model: Thevenin equivalent circuit (e.g. Plett, "Battery Management Systems",
vol. 1, ch. 2):

    V_terminal = OCV(SoC) − I·R0 − V1,     dV1/dt = (I·R1 − V1)/τ

* OCV = cells in series × rest-voltage curve of one cell.
* R0 rises when the pack is colder than 25 °C.
* State of charge: dSoC/dt = −I/Q (coulomb counting).
* Heat: P = I²·R0 + V1²/R1;  C·dT/dt = P − G·(T − T_air).
* BMS: if the current stays beyond the discharge or charge limit for longer
  than the trip delay, the pack is disconnected for the reset time.

Sign convention: current I > 0 discharges the pack. Units: V, A, Ω, s, °C.
"""

from __future__ import annotations

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.lookup import Curve

RESISTANCE_REFERENCE_TEMPERATURE = 25.0  # °C at which the internal resistance is specified


class Battery:
    """The pack. Call :meth:`step` with the total load current each time step."""

    __slots__ = (
        "aux_power", "capacity", "cells", "charge_limit", "chemical_power", "cold_factor",
        "connected", "current", "discharge_limit", "loss_power", "ocv_curve", "over_time",
        "polarisation", "r0", "r1", "reset_time", "soc", "tau", "temperature",
        "thermal_capacity", "thermal_conductance", "trip_delay", "trip_enabled",
        "trip_remaining", "tripped_count", "voltage",
    )

    def __init__(self, params: ParamSet) -> None:
        self.cells = params.integer("battery.cells_series")
        self.capacity = params.num("battery.capacity")  # A·s
        self.ocv_curve = Curve(params.curve("battery.ocv_soc"),
                               params.curve("battery.ocv_cell_voltage"), "battery OCV curve")
        self.r0 = params.num("battery.internal_resistance")
        self.r1 = params.num("battery.polarisation_resistance")
        self.tau = params.num("battery.polarisation_time")
        self.cold_factor = params.num("battery.cold_resistance_factor")
        self.discharge_limit = params.num("battery.bms_discharge_limit")
        self.charge_limit = params.num("battery.bms_charge_limit")
        self.trip_enabled = params.flag("battery.bms_trip_enabled")
        self.trip_delay = params.num("battery.bms_trip_delay")
        self.reset_time = params.num("battery.bms_reset_time")
        self.thermal_capacity = params.num("battery.thermal_capacity")
        self.thermal_conductance = params.num("battery.thermal_conductance")
        self.aux_power = params.num("battery.aux_power")
        self.soc = params.num("battery.initial_soc")
        self.temperature = params.num("environment.air_temperature")
        self.polarisation = 0.0  # V1, V
        self.current = 0.0  # A, + = discharge
        self.voltage = self.open_circuit_voltage()  # terminal voltage, V
        self.connected = True  # False while the BMS has cut the pack off
        self.over_time = 0.0  # s spent beyond a current limit
        self.trip_remaining = 0.0  # s until the BMS reconnects
        self.tripped_count = 0
        self.chemical_power = 0.0  # OCV·I, W drawn from the cells
        self.loss_power = 0.0  # W turned into heat inside the pack

    def open_circuit_voltage(self) -> float:
        """Rest voltage of the pack at the present state of charge, V."""
        return self.cells * self.ocv_curve(self.soc)

    def resistance(self) -> float:
        """Series resistance at the present temperature, Ω."""
        cold = RESISTANCE_REFERENCE_TEMPERATURE - self.temperature
        return self.r0 * (1.0 + self.cold_factor * cold) if cold > 0.0 else self.r0

    def energy_remaining(self) -> float:
        """Energy left above 0 % state of charge at rest voltage, J (coarse estimate)."""
        return self.soc * self.capacity * self.open_circuit_voltage()

    def step(self, dt: float, load_current: float, air_temperature: float) -> None:
        """Advance one step with ``load_current`` (A, + = motors drawing) on the bus."""
        if self.connected:
            current = load_current + self.aux_power / max(self.voltage, 1.0)
        else:
            current = 0.0
            self.trip_remaining -= dt
            if self.trip_remaining <= 0.0:
                self.connected = True
        self.current = current
        r0 = self.resistance()
        ocv = self.open_circuit_voltage()
        self.polarisation += dt * (current * self.r1 - self.polarisation) / self.tau
        self.voltage = ocv - current * r0 - self.polarisation
        self.soc -= current * dt / self.capacity
        if self.soc < 0.0:
            self.soc = 0.0
        elif self.soc > 1.0:
            self.soc = 1.0

        self.chemical_power = ocv * current
        self.loss_power = current * current * r0
        if self.r1 > 0.0:
            self.loss_power += self.polarisation * self.polarisation / self.r1
        self.temperature += dt * (
            self.loss_power - self.thermal_conductance * (self.temperature - air_temperature)
        ) / self.thermal_capacity

        if current > self.discharge_limit or current < -self.charge_limit:
            self.over_time += dt
            if self.trip_enabled and self.connected and self.over_time > self.trip_delay:
                self.connected = False
                self.trip_remaining = self.reset_time
                self.tripped_count += 1
                self.over_time = 0.0
        else:
            self.over_time = 0.0
