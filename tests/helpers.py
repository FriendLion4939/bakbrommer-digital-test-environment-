"""Small helpers shared by the tests."""

from __future__ import annotations

from functools import cache
from typing import Any

from bakbrommer_twin import paths
from bakbrommer_twin.params import REGISTRY, ParamSet
from bakbrommer_twin.params.profile import ProfileStore
from bakbrommer_twin.physics.inputs import DriveCommands, Environment, RiderInputs
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.scenarios.scenario import Scenario, ScenarioStore
from bakbrommer_twin.sim.result import RunResult
from bakbrommer_twin.sim.simulator import run_scenario

SHIPPED_DATA = paths.PROJECT_ROOT / "data"


def scenario(route: list[dict[str, Any]], **fields: Any) -> Scenario:
    """Build a scenario from plain dictionaries."""
    return Scenario.model_validate({"name": "test", "route": route, **fields})


def straight(length_m: float = 500.0, **fields: Any) -> dict[str, Any]:
    """One straight route segment."""
    return {"type": "straight", "length_m": length_m, **fields}


class Rig:
    """A bare vehicle with hand-operated inputs (no driver, sensors or controller)."""

    def __init__(self, params: ParamSet, speed: float = 0.0, gear: int = 1,
                 engine_running: bool = True) -> None:
        self.vehicle = Vehicle(params)
        self.rider = RiderInputs()
        self.rider.gear = gear
        self.commands = DriveCommands()
        self.env = Environment(params.num("environment.air_temperature"))
        self.dt = params.num("sim.time_step")
        self.vehicle.place(0.0, 0.0, 0.0, speed, gear, engine_running)

    def run(self, seconds: float) -> None:
        """Advance the vehicle with the present inputs."""
        for _ in range(round(seconds / self.dt)):
            self.vehicle.step(self.dt, self.rider, self.commands, self.env)

    def set_grade(self, percent: float) -> None:
        """Tilt the road (+ = uphill in the driving direction)."""
        slope = percent / 100.0
        self.env.grade_sin = slope / (1.0 + slope * slope) ** 0.5
        self.env.grade_cos = 1.0 / (1.0 + slope * slope) ** 0.5


@cache
def library_run(key: str, profile: str | None = None) -> RunResult:
    """Run a shipped scenario once per test session (results are cached)."""
    item = ScenarioStore(SHIPPED_DATA / "scenarios").load(key)
    loaded = ProfileStore(SHIPPED_DATA / "profiles", REGISTRY).load(
        profile or item.profile or "default")
    return run_scenario(loaded.params, item, profile_name=loaded.name)
