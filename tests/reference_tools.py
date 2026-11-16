"""Reference values for the scenario regression test.

``collect()`` runs every shipped scenario and extracts the numbers that are
compared against ``tests/reference/scenarios.yaml``. Regenerate that file with
``python scripts/update_reference.py`` after an *intended* change in behaviour
and review the differences before committing.
"""

from __future__ import annotations

from pathlib import Path

from helpers import SHIPPED_DATA, library_run

from bakbrommer_twin.scenarios.scenario import ScenarioStore

REFERENCE_FILE = Path(__file__).parent / "reference" / "scenarios.yaml"
SUMMARY_KEYS = ("duration", "distance", "max_speed", "battery_energy", "fuel_used",
                "peak_battery_current", "max_lateral_accel", "max_roll", "min_rollover_margin",
                "wheel_lift_events", "wheel_lock_events", "bms_trips", "rolled_over")


def scenario_keys() -> list[str]:
    """All shipped scenarios."""
    return ScenarioStore(SHIPPED_DATA / "scenarios").list_keys()


def collect(key: str) -> dict[str, object]:
    """End reason and key numbers (SI) of one shipped scenario."""
    result = library_run(key)
    values: dict[str, float | None] = {m.key: m.value for m in result.meta.metrics}
    values.update({name: result.metric(name) for name in SUMMARY_KEYS})
    rounded = {name: (None if value is None else float(f"{value:.6g}"))
               for name, value in values.items()}
    return {"end_reason": result.meta.end_reason, "values": rounded}
