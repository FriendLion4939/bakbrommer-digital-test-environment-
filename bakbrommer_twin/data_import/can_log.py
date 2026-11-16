"""Reading CAN logs from a CANable adapter: candump text and SavvyCAN CSV.

candump (``candump -l`` / ``-L``)::

    (1699999999.123456) can0 101#E803000000000000

SavvyCAN CSV (time stamp in microseconds, identifier in hex)::

    Time Stamp,ID,Extended,Dir,Bus,LEN,D1,D2,D3,D4,D5,D6,D7,D8
    1000000,00000101,false,Rx,0,8,E8,03,00,00,00,00,00,00
"""

from __future__ import annotations

import re
from typing import NamedTuple

import numpy as np

from bakbrommer_twin.data_import.can_defs import CanDefinitions
from bakbrommer_twin.data_import.rawlog import RawLog
from bakbrommer_twin.params import units

_CANDUMP = re.compile(r"^\((\d+\.\d+)\)\s+\S+\s+([0-9A-Fa-f]+)#([0-9A-Fa-f]*)")
_SAVVY_HEADER = "time stamp,id,extended"
_MICROSECONDS = 1e-6


class Frame(NamedTuple):
    """One CAN frame."""

    time: float  # s
    can_id: int
    data: bytes


def detect_format(text: str) -> str:
    """``"candump"``, ``"savvycan"`` or ``"unknown"`` from the first lines of a file."""
    for line in text.splitlines()[:20]:
        if _CANDUMP.match(line.strip()):
            return "candump"
        if line.strip().lower().startswith(_SAVVY_HEADER):
            return "savvycan"
    return "unknown"


def parse_candump(text: str) -> tuple[list[Frame], int]:
    """Frames of a candump log and the number of unreadable lines."""
    frames, bad = [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        found = _CANDUMP.match(line.strip())
        if not found or len(found.group(3)) % 2:
            bad += 1
            continue
        frames.append(Frame(float(found.group(1)), int(found.group(2), 16),
                            bytes.fromhex(found.group(3))))
    return frames, bad


def parse_savvycan(text: str) -> tuple[list[Frame], int]:
    """Frames of a SavvyCAN CSV export and the number of unreadable lines."""
    frames, bad = [], 0
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.strip().lower().startswith(_SAVVY_HEADER)), -1) + 1
    for line in lines[start:]:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 6 or not parts[0]:
            bad += bool(line.strip())
            continue
        try:
            count = int(parts[5])
            data = bytes(int(byte, 16) for byte in parts[6:6 + count])
            frames.append(Frame(float(parts[0]) * _MICROSECONDS, int(parts[1], 16), data))
        except ValueError:
            bad += 1
    return frames, bad


def parse(text: str) -> tuple[list[Frame], int]:
    """Parse either supported format (detected automatically)."""
    kind = detect_format(text)
    if kind == "candump":
        return parse_candump(text)
    if kind == "savvycan":
        return parse_savvycan(text)
    raise ValueError("This is neither a candump log nor a SavvyCAN CSV file")


def decode_frames(frames: list[Frame], definitions: CanDefinitions, source: str) -> RawLog:
    """Decode frames into a raw log (time starts at the first frame; values in SI)."""
    log = RawLog(source)
    if not frames:
        raise ValueError("the CAN log contains no frames")
    messages = definitions.by_id()
    start = min(frame.time for frame in frames)
    collected: dict[str, tuple[list[float], list[float]]] = {}
    unknown: dict[int, int] = {}
    short = 0
    for frame in frames:
        message = messages.get(frame.can_id)
        if message is None:
            unknown[frame.can_id] = unknown.get(frame.can_id, 0) + 1
            continue
        if len(frame.data) < message.length:
            short += 1
            continue
        for signal in message.signals:
            if signal.channel is None:
                continue
            times, values = collected.setdefault(signal.channel, ([], []))
            times.append(frame.time - start)
            values.append(units.to_si(signal.decode(frame.data[:message.length]), signal.unit))
    for channel, (times, values) in collected.items():
        log.add(channel, np.array(times), np.array(values))
    if unknown:
        listed = ", ".join(f"0x{can_id:X} ({count}×)" for can_id, count in sorted(unknown.items()))
        log.notes.append(f"frames with identifiers not in the definition file: {listed}")
    if short:
        log.notes.append(f"{short} frames were shorter than their definition and were skipped")
    if not log.channels:
        raise ValueError("no frame matched the CAN definition file — wrong definitions?")
    return log
