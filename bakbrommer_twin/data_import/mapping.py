"""Column mappings: which column of a CSV log is which sensor, in which unit.

A mapping is saved as YAML in ``data/mappings`` so the wizard only has to be
filled in once per log format::

    name: STM32F7 SD card log
    time_column: t_ms
    time_unit: ms
    columns:
      - {column: spd_kmh, channel: vehicle_speed, unit: km/h}
      - {column: thr_adc, channel: throttle, unit: "-", scale: 0.000244}   # 12-bit ADC

Value in SI = to_si(raw × scale + offset, unit).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from bakbrommer_twin.data_import.channels import LOG_CHANNELS
from bakbrommer_twin.params import units

_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")
TIME_FACTORS: dict[str, float] = {"s": 1.0, "ms": 1e-3, "us": 1e-6}
# Words that hint at a channel when they appear in a column name (for suggestions).
_HINTS: dict[str, tuple[str, ...]] = {
    "throttle": ("throttle", "thr", "gas", "tps"),
    "brake_front_pressure": ("brake_f", "brk_f", "brakefront", "brake_front", "brake"),
    "brake_rear_pressure": ("brake_r", "brk_r", "brakerear", "brake_rear"),
    "steering_angle": ("steer", "handlebar"),
    "engine_speed": ("engine", "rpm", "eng"),
    "vehicle_speed": ("speed", "spd", "velocity", "gps"),
    "wheel_speed_fl": ("wheel_fl", "ws_fl", "whl_fl", "wfl"),
    "wheel_speed_fr": ("wheel_fr", "ws_fr", "whl_fr", "wfr"),
    "wheel_speed_r": ("wheel_r", "ws_r", "whl_r", "wrear"),
    "accel_x": ("acc_x", "accel_x", "ax"),
    "accel_y": ("acc_y", "accel_y", "ay"),
    "accel_z": ("acc_z", "accel_z", "az"),
    "gyro_x": ("gyro_x", "gyr_x", "gx", "roll_rate"),
    "gyro_y": ("gyro_y", "gyr_y", "gy", "pitch_rate"),
    "gyro_z": ("gyro_z", "gyr_z", "gz", "yaw_rate"),
    "battery_voltage": ("volt", "vbat", "v_bat", "u_bat"),
    "battery_current": ("current", "ibat", "i_bat", "amp"),
    "motor_temp_l": ("temp_l", "tmot_l", "motor_temp_l"),
    "motor_temp_r": ("temp_r", "tmot_r", "motor_temp_r"),
    "ride_mode": ("mode",),
}
_UNIT_HINTS: tuple[tuple[str, str], ...] = (
    ("kmh", "km/h"), ("km/h", "km/h"), ("rpm", "rpm"), ("deg", "deg"), ("pct", "%"),
    ("percent", "%"), ("bar", "bar"), ("dps", "deg/s"), ("rad", "rad"))


class ColumnMap(BaseModel):
    """One mapped column."""

    model_config = ConfigDict(extra="forbid")

    column: str
    channel: str
    unit: str
    scale: float = 1.0
    offset: float = 0.0

    @model_validator(mode="after")
    def _check(self) -> ColumnMap:
        if self.channel not in LOG_CHANNELS:
            raise ValueError(f"unknown channel '{self.channel}'")
        expected = units.si_unit(LOG_CHANNELS[self.channel].unit)
        if units.si_unit(self.unit) != expected:
            usual = LOG_CHANNELS[self.channel].unit
            raise ValueError(f"column '{self.column}': unit '{self.unit}' does not fit channel "
                             f"'{self.channel}' (expected e.g. '{usual}')")
        return self


class LogMapping(BaseModel):
    """How to read one CSV log format."""

    model_config = ConfigDict(extra="forbid")

    name: str
    time_column: str
    time_unit: Literal["s", "ms", "us"] = "s"
    columns: list[ColumnMap] = []


class MappingStore:
    """Loads and saves mappings in one folder."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, key: str) -> Path:
        if not _KEY_PATTERN.match(key):
            raise ValueError(
                f"Mapping file name '{key}' may only contain lower-case letters, digits, _ and -")
        return self.directory / f"{key}.yaml"

    def list_keys(self) -> list[str]:
        """File names (without .yaml) of all saved mappings."""
        return sorted(p.stem for p in self.directory.glob("*.yaml"))

    def load(self, key: str) -> LogMapping:
        """Read one mapping."""
        raw: Any = yaml.safe_load(self._path(key).read_text(encoding="utf-8"))
        return LogMapping.model_validate(raw)

    def save(self, key: str, mapping: LogMapping) -> Path:
        """Write a mapping."""
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        path.write_text(yaml.safe_dump(mapping.model_dump(mode="json"), sort_keys=False,
                                       allow_unicode=True), encoding="utf-8")
        return path


def suggest(columns: list[str]) -> LogMapping:
    """A first guess of the mapping from the column names (the user corrects it)."""
    lowered = {column: column.lower() for column in columns}
    time_column = next((c for c, low in lowered.items()
                        if low.startswith(("time", "t_", "timestamp")) or low == "t"), columns[0])
    low_time = lowered[time_column]
    time_unit: Literal["s", "ms", "us"] = (
        "ms" if "ms" in low_time else ("us" if "us" in low_time else "s"))
    mapped: list[ColumnMap] = []
    taken: set[str] = set()
    for column, low in lowered.items():
        if column == time_column:
            continue
        # the longest matching hint wins, so "brake_r" beats "brake"
        best = max(((len(hint), channel) for channel, hints in _HINTS.items()
                    for hint in hints if hint in low and channel not in taken), default=None)
        if best is None:
            continue
        channel = best[1]
        usual = LOG_CHANNELS[channel].unit
        hinted = next((unit for word, unit in _UNIT_HINTS if word in low), usual)
        unit = hinted if units.si_unit(hinted) == units.si_unit(usual) else usual
        mapped.append(ColumnMap(column=column, channel=channel, unit=unit))
        taken.add(channel)
    return LogMapping(name="suggested", time_column=time_column, time_unit=time_unit,
                      columns=mapped)
