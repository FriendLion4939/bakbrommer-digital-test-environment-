"""Summary numbers calculated for every run (shown at the top of the results)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.battery import Battery
from bakbrommer_twin.sim.result import Metric
from bakbrommer_twin.sim.safety import SafetyEvent

Data = dict[str, NDArray[np.float64]]


def _count(events: list[SafetyEvent], kind: str) -> float:
    return float(sum(1 for event in events if event.kind == kind))


def summarise(data: Data, events: list[SafetyEvent], energy: dict[str, float],
              energy_error: float, params: ParamSet) -> list[Metric]:
    """Build the list of summary metrics (values in SI)."""
    time, speed = data["time"], data["speed"]
    duration = float(time[-1] - time[0])
    # Distance travelled = ∫|v| dt (trapezoidal rule); works with and without a route.
    distance = float(np.trapezoid(np.abs(speed), time))
    battery_energy = energy["battery_chemical"]
    fuel_volume = float(data["fuel_used"][-1])
    per_metre = 1.0 / distance if distance > 1.0 else None
    full_pack = Battery(params)
    full_pack.soc = 1.0
    pack_energy = full_pack.energy_remaining()
    tank = params.num("engine.fuel_tank_volume")
    # Energy that flowed through the vehicle: work put in plus everything dissipated.
    losses = ("brake_loss", "rolling_loss", "drag_loss", "clutch_loss", "gear_loss", "aero_loss",
              "tyre_loss", "damper_loss")
    work = (abs(energy["motor_work"]) + energy["engine_work"] + abs(energy["gravity_work"])
            + sum(abs(energy[name]) for name in losses))

    def rate(total: float) -> float | None:
        return total * per_metre if per_metre is not None else None

    def reach(stock: float, used: float) -> float | None:
        return stock * distance / used if per_metre is not None and used > 0.0 else None

    lift = max(float(np.max(data[f"gap_{name}"])) for name in ("fl", "fr", "r"))
    return [
        Metric(key="duration", label="Duration", value=duration, unit="s"),
        Metric(key="distance", label="Distance", value=distance, unit="m"),
        Metric(key="average_speed", label="Average speed",
               value=distance / duration if duration > 0.0 else 0.0, unit="km/h"),
        Metric(key="max_speed", label="Top speed reached", value=float(np.max(speed)),
               unit="km/h"),
        Metric(key="battery_energy", label="Battery energy used", value=battery_energy,
               unit="Wh"),
        Metric(key="regen_energy", label="Energy recovered", value=energy["regen_energy"],
               unit="Wh"),
        Metric(key="consumption_electric", label="Electric consumption",
               value=rate(battery_energy), unit="Wh/km"),
        Metric(key="fuel_used", label="Fuel used", value=fuel_volume, unit="L"),
        Metric(key="consumption_fuel", label="Fuel consumption", value=rate(fuel_volume),
               unit="L/100km"),
        Metric(key="range_battery", label="Range on a full battery at this pace",
               value=reach(pack_energy, battery_energy), unit="km"),
        Metric(key="range_fuel", label="Range on a full tank at this pace",
               value=reach(tank, fuel_volume), unit="km"),
        Metric(key="soc_end", label="State of charge at the end",
               value=float(data["battery_soc"][-1]), unit="%"),
        Metric(key="peak_battery_current", label="Highest battery current",
               value=float(np.max(data["battery_current"])), unit="A"),
        Metric(key="min_battery_voltage", label="Lowest battery voltage",
               value=float(np.min(data["battery_voltage"])), unit="V"),
        Metric(key="max_motor_temp", label="Highest motor temperature",
               value=float(max(np.max(data["motor_temp_l"]), np.max(data["motor_temp_r"]))),
               unit="°C"),
        Metric(key="max_acceleration", label="Strongest acceleration",
               value=float(np.max(data["accel_x"])), unit="m/s²"),
        Metric(key="max_deceleration", label="Strongest braking",
               value=float(-np.min(data["accel_x"])), unit="m/s²"),
        Metric(key="max_lateral_accel", label="Strongest cornering",
               value=float(np.max(np.abs(data["accel_y"]))), unit="g0"),
        Metric(key="max_roll", label="Largest roll angle",
               value=float(np.max(np.abs(data["roll"]))), unit="deg"),
        Metric(key="min_rollover_margin", label="Smallest rollover margin",
               value=float(np.min(data["rollover_margin"])), unit="-"),
        Metric(key="max_wheel_lift", label="Highest wheel lift", value=lift, unit="mm"),
        Metric(key="wheel_lift_events", label="Wheel lift events",
               value=_count(events, "wheel_lift"), unit="-"),
        Metric(key="wheel_spin_events", label="Wheel spin events",
               value=_count(events, "wheel_spin"), unit="-"),
        Metric(key="wheel_lock_events", label="Wheel lock events",
               value=_count(events, "wheel_lock"), unit="-"),
        Metric(key="overcurrent_events", label="Battery overcurrent events",
               value=_count(events, "battery_overcurrent"), unit="-"),
        Metric(key="bms_trips", label="BMS trips", value=_count(events, "bms_trip"), unit="-"),
        Metric(key="rolled_over", label="Rolled over (1 = yes)",
               value=_count(events, "rollover"), unit="-"),
        Metric(key="energy_balance_error", label="Energy bookkeeping error",
               value=abs(energy_error) / work if work > 0.0 else 0.0, unit="%"),
    ]
