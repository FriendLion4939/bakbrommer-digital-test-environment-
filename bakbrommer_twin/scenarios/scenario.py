"""Scenario files: what to drive, where, and when to stop.

A scenario is a YAML file in ``data/scenarios``. Values use friendly units,
shown in the field names (``length_m``, ``speed_kmh``, ``gradient_pct``).
Example::

    name: Acceleration 0-50 km/h
    category: longitudinal
    route:
      - {type: straight, length_m: 400, speed_kmh: 60, throttle: 1.0}
    end: {time_limit_s: 60, at_speed_kmh: 50}
    metrics:
      - {type: time_to_speed, speed_kmh: 50}
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from bakbrommer_twin.params.definitions.control import RIDE_MODES
from bakbrommer_twin.params.definitions.wheels import SURFACE_NAMES
from bakbrommer_twin.params.types import ParamValue

SegmentType = Literal["straight", "arc", "slalom", "lane_change", "waypoints"]
_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Segment(_Strict):
    """One piece of the route."""

    type: SegmentType = "straight"
    length_m: float | None = Field(default=None, gt=0)  # straight, lane_change
    radius_m: float | None = Field(default=None, gt=0)  # arc
    angle_deg: float | None = None  # arc: + = left turn, − = right turn
    cone_spacing_m: float | None = Field(default=None, gt=0)  # slalom
    cones: int | None = Field(default=None, ge=1)  # slalom
    lateral_offset_m: float | None = None  # slalom amplitude / lane change offset (+ = left)
    points: list[tuple[float, float]] | None = None  # waypoints: [forward m, left m]
    speed_kmh: float = Field(default=30.0, ge=0)  # target speed at the segment start
    speed_end_kmh: float | None = Field(default=None, ge=0)  # ramp to this at the end
    surface: str | None = None  # None = the profile's environment.default_surface
    surface_left: str | None = None  # under the left front wheel, if different
    surface_right: str | None = None  # under the right front wheel, if different
    gradient_pct: float = Field(default=0.0, ge=-40, le=40)  # + = uphill
    throttle: float | None = Field(default=None, ge=0, le=1)  # fixed throttle, no speed control
    brake: float | None = Field(default=None, ge=0, le=1)  # fixed brake lever position
    stop_s: float | None = Field(default=None, gt=0)  # halt this long at the segment start

    @model_validator(mode="after")
    def _check(self) -> Segment:
        needs: dict[str, tuple[str, ...]] = {
            "straight": ("length_m",),
            "arc": ("radius_m", "angle_deg"),
            "slalom": ("cone_spacing_m", "cones", "lateral_offset_m"),
            "lane_change": ("length_m", "lateral_offset_m"),
            "waypoints": ("points",),
        }
        missing = [name for name in needs[self.type] if getattr(self, name) is None]
        if missing:
            raise ValueError(f"a '{self.type}' segment needs: {', '.join(missing)}")
        if self.type == "waypoints" and len(self.points or []) < 2:
            raise ValueError("a 'waypoints' segment needs at least 2 points")
        for name in (self.surface, self.surface_left, self.surface_right):
            if name is not None and name not in SURFACE_NAMES:
                raise ValueError(f"unknown surface '{name}'; choose from {list(SURFACE_NAMES)}")
        return self


class Event(_Strict):
    """Something the rider does at a given time or distance."""

    at_time_s: float | None = Field(default=None, ge=0)
    at_distance_m: float | None = Field(default=None, ge=0)
    set_mode: str

    @model_validator(mode="after")
    def _check(self) -> Event:
        if (self.at_time_s is None) == (self.at_distance_m is None):
            raise ValueError("an event needs exactly one of at_time_s / at_distance_m")
        if self.set_mode not in RIDE_MODES:
            raise ValueError(f"unknown ride mode '{self.set_mode}'; choose from {list(RIDE_MODES)}")
        return self


class Initial(_Strict):
    """State at the start of the run."""

    speed_kmh: float = Field(default=0.0, ge=0)
    ride_mode: str = RIDE_MODES[0]
    engine_running: bool = True

    @model_validator(mode="after")
    def _check(self) -> Initial:
        if self.ride_mode not in RIDE_MODES:
            raise ValueError(f"unknown ride mode '{self.ride_mode}'")
        return self


class EndConditions(_Strict):
    """When the run stops (the end of the route always stops it too)."""

    time_limit_s: float = Field(default=120.0, gt=0)
    at_speed_kmh: float | None = Field(default=None, gt=0)  # stop on reaching this speed
    when_stopped: bool = False  # stop when the vehicle has come to rest (after moving)
    on_wheel_lift: bool = False  # stop at the first reported wheel lift


class MetricSpec(_Strict):
    """A scenario-specific result to calculate (see scenarios/metrics.py)."""

    type: str
    speed_kmh: float | None = None
    from_kmh: float | None = None


class Scenario(_Strict):
    """A complete scenario."""

    name: str
    description: str = ""
    category: str = "general"
    profile: str | None = None  # suggested vehicle profile
    param_overrides: dict[str, ParamValue] = {}  # friendly units, applied on top of the profile
    initial: Initial = Initial()
    route: list[Segment] = Field(min_length=1)
    events: list[Event] = []
    end: EndConditions = EndConditions()
    metrics: list[MetricSpec] = []


class ScenarioStore:
    """Loads and saves scenario files in one folder."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, key: str) -> Path:
        if not _KEY_PATTERN.match(key):
            raise ValueError(
                f"Scenario file name '{key}' may only contain lower-case letters, digits, _ and -")
        return self.directory / f"{key}.yaml"

    def list_keys(self) -> list[str]:
        """File names (without .yaml) of all scenarios, sorted."""
        return sorted(p.stem for p in self.directory.glob("*.yaml"))

    def load(self, key: str) -> Scenario:
        """Read and validate one scenario."""
        path = self._path(key)
        if not path.exists():
            raise ValueError(f"Scenario '{key}' not found in {self.directory}")
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            return Scenario.model_validate(raw)
        except ValueError as exc:
            raise ValueError(f"Scenario '{key}' is not valid: {exc}") from exc

    def save(self, key: str, scenario: Scenario) -> Path:
        """Write a scenario (fields left at their default are omitted)."""
        path = self._path(key)
        self.directory.mkdir(parents=True, exist_ok=True)
        data = scenario.model_dump(mode="json", exclude_defaults=True)
        data.setdefault("name", scenario.name)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")
        return path

    def delete(self, key: str) -> None:
        """Remove a scenario file."""
        self._path(key).unlink()
