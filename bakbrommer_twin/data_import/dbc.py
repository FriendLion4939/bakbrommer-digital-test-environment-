"""Converts a Vector ``.dbc`` file into the program's CAN definitions.

Only the parts needed for decoding are read: messages (``BO_``) and signals
(``SG_``). Multiplexed signals are skipped with a note. After conversion, add
a ``channel:`` to every signal the program should use (the UI offers this).
"""

from __future__ import annotations

import re

from bakbrommer_twin.data_import.can_defs import CanDefinitions, CanMessage, CanSignal
from bakbrommer_twin.data_import.channels import LOG_CHANNELS
from bakbrommer_twin.params import units

_MESSAGE = re.compile(r"^BO_\s+(\d+)\s+(\w+)\s*:\s*(\d+)")
_SIGNAL = re.compile(
    r"^\s*SG_\s+(\w+)\s*(\w*)\s*:\s*(\d+)\|(\d+)@([01])([+-])\s*"
    r"\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)\s*\[[^\]]*\]\s*\"([^\"]*)\"")
_EXTENDED_FLAG = 0x80000000  # DBC marks 29-bit identifiers with bit 31


def parse_dbc(text: str, name: str = "imported") -> tuple[CanDefinitions, list[str]]:
    """Return the definitions and a list of notes about anything skipped."""
    messages: list[CanMessage] = []
    notes: list[str] = []
    current: dict[str, object] | None = None
    signals: list[CanSignal] = []

    def close() -> None:
        if current is not None and signals:
            try:
                messages.append(CanMessage(id=int(str(current["id"])), name=str(current["name"]),
                                           length=int(str(current["length"])),
                                           signals=list(signals)))
            except ValueError as exc:
                notes.append(f"message {current['name']} skipped: {exc}")

    for line in text.splitlines():
        found = _MESSAGE.match(line)
        if found:
            close()
            signals = []
            length = min(8, max(1, int(found.group(3))))
            current = {"id": int(found.group(1)) & ~_EXTENDED_FLAG, "name": found.group(2),
                       "length": length}
            continue
        found = _SIGNAL.match(line)
        if found and current is not None:
            signal_name, multiplex, start, length_bits, order, sign, scale, offset, unit = (
                found.groups())
            if multiplex:
                notes.append(f"signal {signal_name} is multiplexed and was skipped")
                continue
            known_unit = unit if unit in units.UNITS else "-"
            if unit and unit not in units.UNITS:
                notes.append(f"signal {signal_name}: unit '{unit}' is unknown, set it by hand")
            channel = signal_name.lower() if signal_name.lower() in LOG_CHANNELS else None
            if channel and units.si_unit(known_unit) != units.si_unit(LOG_CHANNELS[channel].unit):
                channel = None
            signals.append(CanSignal(
                name=signal_name, start_bit=int(start), length=int(length_bits),
                byte_order="little" if order == "1" else "big", signed=sign == "-",
                scale=float(scale), offset=float(offset), unit=known_unit, channel=channel))
    close()
    return CanDefinitions(name=name, messages=messages), notes
