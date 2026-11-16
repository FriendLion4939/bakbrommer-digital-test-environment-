"""Hard safety constraints used by sweeps, Monte Carlo and the optimiser.

A run "violates" a constraint when one of its summary numbers is beyond the
allowed value. The defaults come from the vehicle parameters (BMS limit,
motor temperature limit); the wheel-lift allowance is the user's choice.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from bakbrommer_twin.params import units
from bakbrommer_twin.params.paramset import ParamSet


class SafetyConstraints(BaseModel):
    """Limits a run must respect to count as safe (SI units)."""

    allow_rollover: bool = False
    max_wheel_lift_events: int = Field(default=0, ge=0)  # reported wheel lifts allowed
    max_wheel_lift: float = Field(default=0.05, ge=0)  # m, highest lift allowed
    max_battery_current: float = Field(default=35.0, gt=0)  # A
    max_motor_temp: float = 140.0  # °C
    allow_bms_trip: bool = False
    min_rollover_margin: float = Field(default=0.0, ge=0, le=1)

    @classmethod
    def from_params(cls, params: ParamSet) -> SafetyConstraints:
        """Constraints with the vehicle's own BMS and motor temperature limits."""
        return cls(max_battery_current=params.num("battery.bms_discharge_limit"),
                   max_motor_temp=params.num("motor.max_temperature"))

    def violations(self, metrics: dict[str, float | None]) -> list[str]:
        """Human-readable list of the constraints a run broke (empty = safe)."""
        def value(key: str) -> float:
            found = metrics.get(key)
            return 0.0 if found is None else found

        broken = []
        if not self.allow_rollover and value("rolled_over") > 0:
            broken.append("rolled over")
        if value("wheel_lift_events") > self.max_wheel_lift_events:
            broken.append(f"{value('wheel_lift_events'):.0f} wheel lift events "
                          f"(allowed {self.max_wheel_lift_events})")
        if value("max_wheel_lift") > self.max_wheel_lift:
            broken.append(f"wheel lifted {units.from_si(value('max_wheel_lift'), 'mm'):.0f} mm "
                          f"(allowed {units.from_si(self.max_wheel_lift, 'mm'):.0f} mm)")
        if value("peak_battery_current") > self.max_battery_current:
            broken.append(f"battery current {value('peak_battery_current'):.0f} A "
                          f"(limit {self.max_battery_current:.0f} A)")
        if value("max_motor_temp") > self.max_motor_temp:
            broken.append(f"motor temperature {value('max_motor_temp'):.0f} °C "
                          f"(limit {self.max_motor_temp:.0f} °C)")
        if not self.allow_bms_trip and value("bms_trips") > 0:
            broken.append("BMS tripped")
        if value("min_rollover_margin") < self.min_rollover_margin:
            broken.append(f"rollover margin {value('min_rollover_margin'):.2f} "
                          f"(required {self.min_rollover_margin:.2f})")
        return broken

    def severity(self, metrics: dict[str, float | None]) -> float:
        """How badly a run breaks the constraints (0 = safe), for ranking unsafe runs."""
        def excess(key: str, limit: float) -> float:
            found = metrics.get(key) or 0.0
            return max(0.0, found / limit - 1.0) if limit > 0.0 else float(found > 0.0)

        total = 0.0
        if not self.allow_rollover:
            total += 10.0 * float((metrics.get("rolled_over") or 0.0) > 0)
        if not self.allow_bms_trip:
            total += 5.0 * float((metrics.get("bms_trips") or 0.0) > 0)
        lifts = (metrics.get("wheel_lift_events") or 0.0) - self.max_wheel_lift_events
        total += max(0.0, lifts)
        total += excess("max_wheel_lift", self.max_wheel_lift)
        total += excess("peak_battery_current", self.max_battery_current)
        total += excess("max_motor_temp", self.max_motor_temp)
        margin = metrics.get("min_rollover_margin")
        if margin is not None and margin < self.min_rollover_margin:
            total += self.min_rollover_margin - margin
        return total
