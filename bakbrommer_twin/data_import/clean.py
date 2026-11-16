"""Cleaning a raw log: bad data out, resample, filter, align, quality report.

Steps of :func:`clean`:
1. Samples outside a channel's plausible range are rejected.
2. Each channel is resampled to one uniform time grid by linear
   interpolation.
3. Where the log has a gap (no sample for longer than the gap threshold) the
   grid samples are marked missing (NaN) — nothing is invented across gaps.
4. Optional zero-phase low-pass filter (Butterworth, applied forwards and
   backwards so signals are not delayed), per gap-free stretch.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field
from scipy import signal

from bakbrommer_twin.data_import.channels import LOG_CHANNELS, MODE_CHANNEL
from bakbrommer_twin.data_import.rawlog import RawLog
from bakbrommer_twin.data_import.recording import Recording

Array = NDArray[np.float64]
_FILTER_ORDER = 2
_MIN_FILTER_SAMPLES = 15  # filtfilt needs a few samples to work with


class CleanOptions(BaseModel):
    """Settings of the cleaning step."""

    rate_hz: float = Field(default=100.0, gt=0, le=2000)  # grid of the cleaned recording
    gap_s: float = Field(default=0.5, gt=0)  # longer pauses in a channel count as a gap
    lowpass_hz: float | None = Field(default=None, gt=0)  # None = no filtering


@dataclass(frozen=True)
class ChannelQuality:
    """What happened to one channel during cleaning."""

    channel: str
    samples: int  # samples in the file
    rejected: int  # outside the plausible range
    gaps: int  # number of gaps
    longest_gap: float  # s
    coverage: float  # share of the cleaned grid that is valid, 0…1
    rate: float  # typical sample rate in the file, Hz


def _runs(mask: Array) -> list[tuple[int, int]]:
    """Start/stop index pairs of the True stretches of a boolean array."""
    padded = np.concatenate(([False], mask.astype(bool), [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(edges[::2].tolist(), edges[1::2].tolist(), strict=True))


def _lowpass(values: Array, rate: float, cutoff: float) -> Array:
    if cutoff >= 0.5 * rate:
        return values
    b, a = signal.butter(_FILTER_ORDER, cutoff, fs=rate)
    result = values.copy()
    for start, stop in _runs(np.isfinite(values)):
        if stop - start >= _MIN_FILTER_SAMPLES:
            result[start:stop] = signal.filtfilt(b, a, values[start:stop])
    return result


def clean(raw: RawLog, options: CleanOptions | None = None,
          ) -> tuple[Recording, list[ChannelQuality]]:
    """Turn a raw log into a uniform recording plus a quality report."""
    settings = options or CleanOptions()
    start = raw.start_time()
    end = max(float(t[-1]) for t, _ in raw.channels.values() if len(t))
    grid = np.arange(0.0, end - start + 0.5 / settings.rate_hz, 1.0 / settings.rate_hz)
    recording = Recording(raw.source, settings.rate_hz, synthetic=raw.synthetic,
                          notes=list(raw.notes))
    report = []
    for name, (stamps, values) in raw.channels.items():
        channel = LOG_CHANNELS[name]
        time = stamps - start
        good = (values >= channel.low) & (values <= channel.high)
        rejected = int((~good).sum())
        time, kept = time[good], values[good]
        resampled = np.full(len(grid), np.nan)
        gaps, longest, rate = 0, 0.0, 0.0
        if len(time) >= 2:
            steps = np.diff(time)
            rate = float(1.0 / np.median(steps)) if np.median(steps) > 0 else 0.0
            if name == MODE_CHANNEL:  # a switch position: hold, do not interpolate
                resampled = kept[np.clip(np.searchsorted(time, grid, side="right") - 1, 0,
                                         len(kept) - 1)]
            else:
                resampled = np.interp(grid, time, kept)
            resampled[(grid < time[0]) | (grid > time[-1])] = np.nan
            for i in np.flatnonzero(steps > settings.gap_s):
                resampled[(grid > time[i]) & (grid < time[i + 1])] = np.nan
                gaps += 1
                longest = max(longest, float(steps[i]))
            if settings.lowpass_hz is not None and name != MODE_CHANNEL:
                resampled = _lowpass(resampled, settings.rate_hz, settings.lowpass_hz)
        recording.data[name] = resampled
        report.append(ChannelQuality(name, len(values), rejected, gaps, longest,
                                     float(np.mean(np.isfinite(resampled))), rate))
    return recording, report


def align_offset(reference: RawLog, other: RawLog, channel: str, rate_hz: float = 50.0,
                 max_shift_s: float = 30.0) -> float:
    """Seconds to add to ``other``'s time stamps so its ``channel`` lines up with ``reference``.

    Both logs must contain ``channel`` (e.g. vehicle speed in the SD-card log
    and in the CAN log). The offset is the lag with the highest
    cross-correlation of the two signals (mean removed).
    """
    for log in (reference, other):
        if channel not in log.channels:
            raise ValueError(f"both logs need the channel '{channel}' to be aligned")
    t_ref, v_ref = reference.channels[channel]
    t_other, v_other = other.channels[channel]
    step = 1.0 / rate_hz
    grid_ref = np.arange(t_ref[0], t_ref[-1], step)
    grid_other = np.arange(t_other[0], t_other[-1], step)
    a = np.interp(grid_ref, t_ref, v_ref)
    b = np.interp(grid_other, t_other, v_other)
    a, b = a - a.mean(), b - b.mean()
    correlation = signal.correlate(a, b, mode="full")
    lags = signal.correlation_lags(len(a), len(b), mode="full") * step
    start_difference = float(t_ref[0] - t_other[0])
    allowed = np.abs(lags + start_difference) <= max_shift_s
    if not allowed.any():
        raise ValueError("the two logs do not overlap within the allowed shift")
    best = lags[allowed][int(np.argmax(correlation[allowed]))]
    return float(best + start_difference)
