"""A complete set of parameter values (one vehicle configuration in memory)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from bakbrommer_twin.params import units
from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Kind, ParamError, ParamValue, Status


class ParamSet:
    """Values (SI) and statuses for every parameter in a registry.

    Code reads values through the typed accessors :meth:`num`, :meth:`integer`,
    :meth:`flag`, :meth:`choice` and :meth:`curve`. Unknown names raise
    :class:`ParamError`, so a typing mistake fails loudly instead of silently.
    """

    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self._values: dict[str, ParamValue] = {d.name: _clone(d.default) for d in registry}
        self._status: dict[str, Status] = {d.name: d.status for d in registry}
        self._accessed: set[str] = set()

    # ---- typed read access (SI units) -------------------------------------------

    def _get(self, name: str, kind: Kind) -> ParamValue:
        definition = self.registry.get(name)
        if definition.kind is not kind:
            raise ParamError(f"Parameter '{name}' is a {definition.kind}, not a {kind}")
        self._accessed.add(name)
        return self._values[name]

    def num(self, name: str) -> float:
        """A real number in SI units."""
        return cast(float, self._get(name, Kind.NUMBER))

    def integer(self, name: str) -> int:
        """A whole number."""
        return cast(int, self._get(name, Kind.INTEGER))

    def flag(self, name: str) -> bool:
        """A yes/no switch."""
        return cast(bool, self._get(name, Kind.FLAG))

    def choice(self, name: str) -> str:
        """One of a fixed list of options."""
        return cast(str, self._get(name, Kind.CHOICE))

    def curve(self, name: str) -> list[float]:
        """A list of numbers in SI units (a copy; safe to modify)."""
        return list(cast(list[float], self._get(name, Kind.CURVE)))

    def value(self, name: str) -> ParamValue:
        """The SI value whatever its kind (for generic code such as the UI)."""
        self.registry.get(name)
        return _clone(self._values[name])

    def status(self, name: str) -> Status:
        """The trust status of the current value."""
        self.registry.get(name)
        return self._status[name]

    def accessed_names(self) -> set[str]:
        """Names read so far through the typed accessors (used to find unused parameters)."""
        return set(self._accessed)

    # ---- write access ---------------------------------------------------------------

    def set(self, name: str, value: ParamValue, status: Status | None = None) -> None:
        """Set an SI value (validated). Optionally update its status."""
        self._values[name] = self.registry.validate(name, _clone(value))
        if status is not None:
            self._status[name] = status

    def set_status(self, name: str, status: Status) -> None:
        """Change only the status of a parameter."""
        self.registry.get(name)
        self._status[name] = status

    # ---- friendly-unit access (UI, YAML, import/export) -----------------------------

    def display(self, name: str) -> ParamValue:
        """The value converted to the parameter's friendly unit."""
        d = self.registry.get(name)
        value = self._values[name]
        if d.kind is Kind.NUMBER:
            return units.from_si(cast(float, value), d.unit)
        if d.kind is Kind.CURVE:
            return units.list_from_si(cast(list[float], value), d.unit)
        return _clone(value)

    def set_display(self, name: str, value: ParamValue, status: Status | None = None) -> None:
        """Set a value given in the parameter's friendly unit."""
        d = self.registry.get(name)
        if d.kind is Kind.NUMBER and isinstance(value, int | float) and not isinstance(value, bool):
            self.set(name, units.to_si(float(value), d.unit), status)
        elif d.kind is Kind.CURVE and isinstance(value, list):
            self.set(name, units.list_to_si(value, d.unit), status)
        else:
            self.set(name, value, status)

    # ---- whole-set operations ----------------------------------------------------------

    def copy(self) -> ParamSet:
        """An independent copy."""
        other = ParamSet(self.registry)
        other._values = {k: _clone(v) for k, v in self._values.items()}
        other._status = dict(self._status)
        return other

    def with_display_overrides(self, overrides: Mapping[str, ParamValue]) -> ParamSet:
        """A copy with some values replaced (given in friendly units)."""
        other = self.copy()
        for name, value in overrides.items():
            other.set_display(name, value)
        return other

    def differences(self, other: ParamSet) -> list[str]:
        """Names whose value or status differs between this set and ``other``."""
        return [
            name
            for name in self.registry.names()
            if not _same(self._values[name], other._values[name])
            or self._status[name] != other._status[name]
        ]

    def value_differences(self, other: ParamSet) -> list[str]:
        """Names whose value differs between this set and ``other``."""
        return [
            name
            for name in self.registry.names()
            if not _same(self._values[name], other._values[name])
        ]

    def as_display_dict(self) -> dict[str, ParamValue]:
        """All values in friendly units (for snapshots stored with a run)."""
        return {name: self.display(name) for name in self.registry.names()}


def _clone(value: ParamValue) -> ParamValue:
    return list(value) if isinstance(value, list) else value


def _same(a: ParamValue, b: ParamValue) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str):
        return a == b
    fa, fb = float(cast(float, a)), float(cast(float, b))
    return abs(fa - fb) <= 1e-9 * max(1.0, abs(fa), abs(fb))
