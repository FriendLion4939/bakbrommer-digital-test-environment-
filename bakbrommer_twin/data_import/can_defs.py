"""CAN message definitions (DBC-style) in an editable YAML file.

Example (``data/can/*.yaml``)::

    name: Bakbrommer example bus
    bitrate: 500000
    messages:
      - id: 0x101
        name: RIDER_INPUTS
        signals:
          - {name: throttle, channel: throttle, start_bit: 0, length: 16,
             scale: 0.01, unit: "%"}

A signal's physical value is ``raw × scale + offset`` in ``unit``; ``channel``
says which log channel it is (omit it for signals the program should ignore).

Bit numbering follows the DBC convention:
* ``byte_order: little`` (Intel): ``start_bit`` is the least significant bit;
  bit n is bit (n mod 8) of byte (n div 8).
* ``byte_order: big`` (Motorola): ``start_bit`` is the most significant bit in
  the same numbering; the value continues towards higher byte numbers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from bakbrommer_twin.data_import.channels import LOG_CHANNELS
from bakbrommer_twin.params import units


class CanSignal(BaseModel):
    """One value inside a CAN message."""

    model_config = ConfigDict(extra="forbid")

    name: str
    start_bit: int = Field(ge=0, le=63)
    length: int = Field(ge=1, le=64)
    byte_order: Literal["little", "big"] = "little"
    signed: bool = False
    scale: float = 1.0
    offset: float = 0.0
    unit: str = "-"
    channel: str | None = None  # canonical log channel, None = not used

    @model_validator(mode="after")
    def _check(self) -> CanSignal:
        if self.channel is not None:
            if self.channel not in LOG_CHANNELS:
                raise ValueError(f"signal '{self.name}': unknown channel '{self.channel}'")
            expected = units.si_unit(LOG_CHANNELS[self.channel].unit)
            if units.si_unit(self.unit) != expected:
                raise ValueError(f"signal '{self.name}': unit '{self.unit}' does not fit "
                                 f"channel '{self.channel}'")
        return self

    def _shift(self, size: int) -> int:
        """How far the raw value sits above bit 0 of the message read as one integer."""
        if self.byte_order == "little":
            return self.start_bit
        from_top = (self.start_bit // 8) * 8 + (7 - self.start_bit % 8)
        return size * 8 - from_top - self.length

    def decode(self, data: bytes) -> float:
        """Physical value (in ``unit``) of this signal in a message payload."""
        number = int.from_bytes(data, self.byte_order)
        raw = (number >> self._shift(len(data))) & ((1 << self.length) - 1)
        if self.signed and raw >= 1 << (self.length - 1):
            raw -= 1 << self.length
        return raw * self.scale + self.offset

    def encode_into(self, number: int, value: float, size: int) -> int:
        """Write a physical value into a message integer (inverse of :meth:`decode`)."""
        raw = round((value - self.offset) / self.scale)
        low = -(1 << (self.length - 1)) if self.signed else 0
        high = (1 << (self.length - 1)) - 1 if self.signed else (1 << self.length) - 1
        raw = min(high, max(low, raw)) & ((1 << self.length) - 1)
        return number | (raw << self._shift(size))


class CanMessage(BaseModel):
    """One CAN frame layout."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=0, le=0x1FFFFFFF)
    name: str
    length: int = Field(default=8, ge=1, le=8)  # payload bytes
    signals: list[CanSignal]

    def decode(self, data: bytes) -> dict[str, float]:
        """All signal values of a payload by signal name."""
        return {signal.name: signal.decode(data) for signal in self.signals}

    def encode(self, values: dict[str, float]) -> bytes:
        """Build a payload from physical values (missing signals are zero)."""
        number = 0
        for signal in self.signals:
            number = signal.encode_into(number, values.get(signal.name, 0.0), self.length)
        order: Literal["little", "big"] = self.signals[0].byte_order if self.signals else "little"
        return number.to_bytes(self.length, order)

    @model_validator(mode="after")
    def _one_byte_order(self) -> CanMessage:
        if len({signal.byte_order for signal in self.signals}) > 1:
            raise ValueError(f"message '{self.name}': all signals must use the same byte order")
        return self


class CanDefinitions(BaseModel):
    """All messages of one bus."""

    model_config = ConfigDict(extra="forbid")

    name: str
    bitrate: int = 500_000
    messages: list[CanMessage]

    def by_id(self) -> dict[int, CanMessage]:
        """Messages by CAN identifier."""
        return {message.id: message for message in self.messages}


def load_definitions(path: Path) -> CanDefinitions:
    """Read a CAN definition YAML file."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CanDefinitions.model_validate(raw)


def save_definitions(path: Path, definitions: CanDefinitions) -> None:
    """Write a CAN definition YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = definitions.model_dump(mode="json", exclude_defaults=True)
    data.setdefault("name", definitions.name)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
