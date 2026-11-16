"""Reading CSV logs (e.g. from the STM32F7 SD card) with a column mapping."""

from __future__ import annotations

import csv
import io

import numpy as np
import pandas as pd

from bakbrommer_twin.data_import.mapping import TIME_FACTORS, LogMapping
from bakbrommer_twin.data_import.rawlog import RawLog
from bakbrommer_twin.params import units

_SNIFF_BYTES = 4096


def read_table(text: str) -> pd.DataFrame:
    """Parse CSV text into a table; separator (, ; tab) and decimal comma are detected."""
    sample = text[:_SNIFF_BYTES]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ","
    decimal = "," if delimiter == ";" else "."
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    frame = pd.read_csv(io.StringIO("\n".join(lines)), sep=delimiter, decimal=decimal,
                        skipinitialspace=True)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def apply_mapping(frame: pd.DataFrame, mapping: LogMapping, source: str) -> RawLog:
    """Turn a table into a raw log using a column mapping (values converted to SI)."""
    if mapping.time_column not in frame.columns:
        raise ValueError(f"time column '{mapping.time_column}' is not in the file "
                         f"(columns: {list(frame.columns)})")
    time = pd.to_numeric(frame[mapping.time_column], errors="coerce").to_numpy(dtype=float)
    time = time * TIME_FACTORS[mapping.time_unit]
    log = RawLog(source)
    bad_time = ~np.isfinite(time)
    if bad_time.any():
        log.notes.append(f"{int(bad_time.sum())} rows without a valid time stamp were skipped")
    for item in mapping.columns:
        if item.column not in frame.columns:
            raise ValueError(f"mapped column '{item.column}' is not in the file")
        raw = pd.to_numeric(frame[item.column], errors="coerce").to_numpy(dtype=float)
        _, factor, shift = units.UNITS[item.unit]
        values = (raw * item.scale + item.offset) * factor + shift
        keep = ~bad_time & np.isfinite(values)
        dropped = int((~bad_time & ~np.isfinite(values)).sum())
        if dropped:
            log.notes.append(f"column '{item.column}': {dropped} unreadable values skipped")
        log.add(item.channel, time[keep], values[keep])
    if not log.channels:
        raise ValueError("the mapping does not map any column")
    return log
