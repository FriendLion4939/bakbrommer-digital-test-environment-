"""Performance check: how long does a 10-minute ride take to simulate?

Requirement: a 10-minute ride at a 1 ms step simulates in well under a minute.

Usage:  python scripts/performance_check.py
"""

from __future__ import annotations

import time

from bakbrommer_twin.params import default_params
from bakbrommer_twin.scenarios.scenario import Scenario
from bakbrommer_twin.sim.simulator import run_scenario

RIDE_SECONDS = 600.0
# A mixed loop (town speed, 50 km/h stretch, hill, bends, a stop), repeated.
_LOOP = [
    {"type": "straight", "length_m": 300, "speed_kmh": 30},
    {"type": "arc", "radius_m": 15, "angle_deg": 90, "speed_kmh": 30},
    {"type": "straight", "length_m": 700, "speed_kmh": 50},
    {"type": "straight", "length_m": 400, "speed_kmh": 45, "gradient_pct": 4, "stop_s": 5},
    {"type": "arc", "radius_m": 20, "angle_deg": 180, "speed_kmh": 40},
    {"type": "straight", "length_m": 400, "speed_kmh": 45, "gradient_pct": -4},
    {"type": "straight", "length_m": 700, "speed_kmh": 50},
    {"type": "arc", "radius_m": 15, "angle_deg": 90, "speed_kmh": 30},
]


def measure(ride_seconds: float = RIDE_SECONDS) -> tuple[float, float, float]:
    """Simulate the ride; return (simulated s, wall-clock s, time step s)."""
    scenario = Scenario.model_validate({
        "name": "Performance check", "route": _LOOP * 4,
        "end": {"time_limit_s": ride_seconds}})
    params = default_params()
    start = time.perf_counter()
    result = run_scenario(params, scenario)
    return result.meta.duration, time.perf_counter() - start, result.meta.time_step


def main() -> None:
    """Run the check and print the result."""
    simulated, wall, step = measure()
    per_step = wall / (simulated / step) * 1e6
    print(f"Simulated {simulated:.0f} s of riding at a {step * 1000:g} ms step in {wall:.1f} s "
          f"({simulated / wall:.0f}x real time, {per_step:.0f} µs per step).")
    print("Requirement (well under a minute for 10 minutes): "
          + ("met." if wall < 45.0 and simulated >= RIDE_SECONDS else "NOT met."))


if __name__ == "__main__":
    main()
