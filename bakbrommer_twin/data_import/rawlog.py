"""A log as read from a file: every channel with its own time stamps."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


@dataclass
class RawLog:
    """Channel name → (time stamps in s, values in SI). Not yet cleaned."""

    source: str  # file name, for reports
    channels: dict[str, tuple[Array, Array]] = field(default_factory=dict)
    synthetic: bool = False  # True for simulator-generated example data
    notes: list[str] = field(default_factory=list)  # what the reader noticed

    def add(self, name: str, time: Array, values: Array) -> None:
        """Add (or extend) a channel; samples are kept sorted by time."""
        if name in self.channels:
            old_time, old_values = self.channels[name]
            time = np.concatenate([old_time, time])
            values = np.concatenate([old_values, values])
        order = np.argsort(time, kind="stable")
        self.channels[name] = (time[order], values[order])

    def start_time(self) -> float:
        """Earliest time stamp of any channel, s."""
        return min(float(t[0]) for t, _ in self.channels.values() if len(t))

    def shifted(self, seconds: float) -> RawLog:
        """A copy with all time stamps moved by ``seconds``."""
        return RawLog(self.source, {name: (t + seconds, v) for name, (t, v)
                                    in self.channels.items()}, self.synthetic, list(self.notes))

    def merged(self, other: RawLog) -> RawLog:
        """This log plus the channels of ``other`` (same clock assumed)."""
        result = RawLog(f"{self.source} + {other.source}", dict(self.channels),
                        self.synthetic or other.synthetic, [*self.notes, *other.notes])
        for name, (time, values) in other.channels.items():
            result.add(name, time, values)
        return result
