"""Energy bookkeeping: where every joule comes from and goes to.

The vehicle model adds to these totals each step. Tests use
:meth:`EnergyLedger.mechanical_error` to check that the dynamics conserve
energy; reports use the totals for consumption figures and loss breakdowns.
All values in joules.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(slots=True)
class EnergyLedger:
    """Running energy totals of one simulation, J."""

    # mechanical work put into the vehicle
    motor_work: float = 0.0  # electromagnetic motor torque × wheel speed
    engine_work: float = 0.0  # net crankshaft torque × engine speed
    gravity_work: float = 0.0  # + downhill, − uphill
    # mechanical losses (all ≥ 0 in normal driving)
    brake_loss: float = 0.0
    rolling_loss: float = 0.0
    drag_loss: float = 0.0  # motor drag and driveline drag
    clutch_loss: float = 0.0
    gear_loss: float = 0.0
    aero_loss: float = 0.0
    tyre_loss: float = 0.0  # tyre slip (drive, brake and cornering)
    damper_loss: float = 0.0
    # electrical and fuel
    battery_chemical: float = 0.0  # drawn from the cells (OCV × current)
    battery_loss: float = 0.0  # heat inside the pack
    bus_energy: float = 0.0  # delivered to the motor controllers (net of regen)
    regen_energy: float = 0.0  # returned to the bus by the motors
    aux_energy: float = 0.0
    motor_loss: float = 0.0  # copper losses in the motors
    fuel_energy: float = 0.0  # heating value of the fuel burnt

    def mechanical_input(self) -> float:
        """Work put into the vehicle's mechanical energy, J."""
        return self.motor_work + self.engine_work + self.gravity_work

    def mechanical_losses(self) -> float:
        """Mechanical energy turned into heat, J."""
        return (self.brake_loss + self.rolling_loss + self.drag_loss + self.clutch_loss
                + self.gear_loss + self.aero_loss + self.tyre_loss + self.damper_loss)

    def mechanical_error(self, energy_start: float, energy_end: float) -> float:
        """Energy that is unaccounted for: Δstored − (input − losses), J."""
        return (energy_end - energy_start) - (self.mechanical_input() - self.mechanical_losses())

    def as_dict(self) -> dict[str, float]:
        """All totals by name."""
        return {f.name: float(getattr(self, f.name)) for f in fields(self)}
