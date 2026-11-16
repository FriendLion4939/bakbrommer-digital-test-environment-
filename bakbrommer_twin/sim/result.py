"""The result of one simulation run and how it is stored on disk.

A saved run is a folder with ``meta.json`` (everything except the signals)
and ``channels.npz`` (the recorded signals in SI units).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pydantic import BaseModel

from bakbrommer_twin.params import units
from bakbrommer_twin.params.types import ParamValue
from bakbrommer_twin.sim.channels import ChannelDef
from bakbrommer_twin.sim.safety import SafetyEvent

META_FILE = "meta.json"
CHANNELS_FILE = "channels.npz"


class ChannelInfo(BaseModel):
    """Display information of one recorded channel."""

    name: str
    unit: str
    label: str
    group: str

    @classmethod
    def from_def(cls, definition: ChannelDef) -> ChannelInfo:
        """Copy the fields of a :class:`ChannelDef`."""
        return cls(name=definition.name, unit=definition.unit, label=definition.label,
                   group=definition.group)


class Metric(BaseModel):
    """One named result number (value in SI, shown in ``unit``)."""

    key: str
    label: str
    value: float | None  # None = could not be determined (e.g. speed never reached)
    unit: str

    def display(self) -> float | None:
        """The value in its friendly unit."""
        return None if self.value is None else units.from_si(self.value, self.unit)


class RunMeta(BaseModel):
    """Everything about a run except the recorded signals."""

    name: str  # label shown in the UI
    scenario_name: str
    scenario: dict[str, object]  # the scenario as run (for reproducing)
    profile_name: str
    validated: bool  # False = profile not calibrated against real data
    controller: str
    created: str  # ISO time stamp
    time_step: float  # s
    duration: float  # s simulated
    end_reason: str
    params: dict[str, ParamValue]  # all parameter values (friendly units)
    channels: list[ChannelInfo]
    events: list[SafetyEvent]
    energy: dict[str, float]  # energy ledger totals, J
    summary: list[Metric]
    metrics: list[Metric]  # scenario-specific results


class RunResult:
    """A finished run: metadata plus the recorded signals."""

    def __init__(self, meta: RunMeta, data: dict[str, NDArray[np.float64]]) -> None:
        self.meta = meta
        self.data = data  # channel name -> samples (SI)

    def __getitem__(self, channel: str) -> NDArray[np.float64]:
        return self.data[channel]

    def info(self, channel: str) -> ChannelInfo:
        """Display information of a channel."""
        for item in self.meta.channels:
            if item.name == channel:
                return item
        raise KeyError(channel)

    def display(self, channel: str) -> NDArray[np.float64]:
        """Samples of a channel converted to its friendly unit."""
        unit = self.info(channel).unit
        _, factor, offset = units.UNITS[unit]
        return np.asarray((self.data[channel] - offset) / factor)

    def to_dataframe(self) -> pd.DataFrame:
        """All channels in friendly units, columns named ``name [unit]``."""
        return pd.DataFrame({
            f"{item.name} [{item.unit}]" if item.unit not in ("", "-") else item.name:
                self.display(item.name)
            for item in self.meta.channels
        })

    def metric(self, key: str) -> float | None:
        """SI value of a summary or scenario metric by key."""
        for item in (*self.meta.metrics, *self.meta.summary):
            if item.key == key:
                return item.value
        raise KeyError(key)

    # ---- disk ---------------------------------------------------------------------

    def save(self, runs_dir: Path) -> Path:
        """Store the run in a new folder under ``runs_dir``; return the folder."""
        slug = re.sub(r"[^a-z0-9]+", "-", self.meta.name.lower()).strip("-") or "run"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        folder = runs_dir / f"{stamp}-{slug}"
        folder.mkdir(parents=True)
        (folder / META_FILE).write_text(self.meta.model_dump_json(indent=1), encoding="utf-8")
        np.savez_compressed(folder / CHANNELS_FILE, **self.data)  # type: ignore[arg-type]
        return folder

    @classmethod
    def load(cls, folder: Path) -> RunResult:
        """Read a run saved with :meth:`save`."""
        meta = RunMeta.model_validate(json.loads((folder / META_FILE).read_text("utf-8")))
        with np.load(folder / CHANNELS_FILE) as stored:
            data = {name: np.asarray(stored[name], dtype=np.float64) for name in stored.files}
        return cls(meta, data)


def list_runs(runs_dir: Path) -> list[Path]:
    """Folders of all saved runs, newest first."""
    return sorted((p for p in runs_dir.iterdir() if (p / META_FILE).exists()), reverse=True)
