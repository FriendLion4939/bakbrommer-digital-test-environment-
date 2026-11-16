"""A cleaned ride recording: all channels on one uniform time grid.

Samples that are missing or were rejected are NaN ("not a number"), so later
steps can simply skip them. A recording can be stored in ``data/recordings``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]
_META_FILE = "meta.json"
_DATA_FILE = "data.npz"
_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


@dataclass
class Recording:
    """Channels (SI units) sampled at a fixed rate, starting at time 0."""

    source: str
    rate: float  # Hz
    data: dict[str, Array] = field(default_factory=dict)
    synthetic: bool = False  # True for simulator-generated example data
    notes: list[str] = field(default_factory=list)

    @property
    def samples(self) -> int:
        """Number of samples."""
        return len(next(iter(self.data.values()))) if self.data else 0

    @property
    def time(self) -> Array:
        """Time of every sample, s."""
        return np.arange(self.samples) / self.rate

    @property
    def duration(self) -> float:
        """Length of the recording, s."""
        return max(0.0, (self.samples - 1) / self.rate)

    def coverage(self, channel: str) -> float:
        """Share of valid samples of a channel (0…1)."""
        return float(np.mean(np.isfinite(self.data[channel]))) if self.samples else 0.0

    def filled(self, channel: str, default: float = 0.0) -> Array:
        """A channel with gaps bridged by holding the last valid value."""
        values = self.data[channel].copy()
        valid = np.isfinite(values)
        if not valid.any():
            return np.full_like(values, default)
        index = np.where(valid, np.arange(len(values)), 0)
        np.maximum.accumulate(index, out=index)
        held = values[index]
        held[: int(np.argmax(valid))] = values[valid][0]
        return np.asarray(held)

    def save(self, directory: Path, key: str) -> Path:
        """Store the recording in ``directory/key``."""
        if not _KEY_PATTERN.match(key):
            raise ValueError(
                f"Recording name '{key}' may only contain lower-case letters, digits, _ and -")
        folder = directory / key
        folder.mkdir(parents=True, exist_ok=True)
        meta = {"source": self.source, "rate": self.rate, "synthetic": self.synthetic,
                "notes": self.notes}
        (folder / _META_FILE).write_text(json.dumps(meta, indent=1), encoding="utf-8")
        np.savez_compressed(folder / _DATA_FILE, **self.data)  # type: ignore[arg-type]
        return folder

    @classmethod
    def load(cls, folder: Path) -> Recording:
        """Read a recording stored with :meth:`save`."""
        meta = json.loads((folder / _META_FILE).read_text(encoding="utf-8"))
        with np.load(folder / _DATA_FILE) as stored:
            data = {name: np.asarray(stored[name], dtype=np.float64) for name in stored.files}
        return cls(meta["source"], float(meta["rate"]), data, bool(meta["synthetic"]),
                   list(meta["notes"]))


def list_recordings(directory: Path) -> list[str]:
    """Names of the stored recordings."""
    if not directory.exists():
        return []
    return sorted(p.name for p in directory.iterdir() if (p / _META_FILE).exists())
