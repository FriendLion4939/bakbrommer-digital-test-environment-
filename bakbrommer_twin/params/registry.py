"""The parameter registry: the single list of every adjustable value.

Parameters are declared in ``params/definitions/*.py`` by calling the helper
methods of :class:`Registry`. Definition authors write values in a friendly
unit; the registry converts them to SI once, here.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from difflib import get_close_matches

from bakbrommer_twin.params import units
from bakbrommer_twin.params.types import Kind, ParamDef, ParamError, ParamValue, Status


class Registry:
    """Ordered collection of :class:`ParamDef`, looked up by dotted name."""

    def __init__(self) -> None:
        self._defs: dict[str, ParamDef] = {}
        self._category_labels: dict[str, str] = {}

    # ---- declaring parameters -------------------------------------------------

    def category(self, key: str, label: str) -> None:
        """Declare a category (UI tab) with its human-readable title."""
        self._category_labels[key] = label

    def _add(self, definition: ParamDef) -> None:
        if definition.name in self._defs:
            raise ParamError(f"Parameter '{definition.name}' is defined twice")
        if definition.category not in self._category_labels:
            raise ParamError(
                f"Parameter '{definition.name}': declare category "
                f"'{definition.category}' with registry.category() first"
            )
        self._defs[definition.name] = definition

    def number(
        self,
        name: str,
        default: float,
        unit: str,
        lo: float,
        hi: float,
        label: str,
        description: str,
        status: Status = Status.DEFAULT,
    ) -> None:
        """Declare a real number. ``default``, ``lo`` and ``hi`` are in ``unit``."""
        self._add(
            ParamDef(
                name=name,
                label=label,
                description=description,
                kind=Kind.NUMBER,
                default=units.to_si(default, unit),
                unit=unit,
                si_unit=units.si_unit(unit),
                min=units.to_si(lo, unit),
                max=units.to_si(hi, unit),
                status=status,
            )
        )

    def integer(
        self,
        name: str,
        default: int,
        lo: int,
        hi: int,
        label: str,
        description: str,
        status: Status = Status.DEFAULT,
    ) -> None:
        """Declare a whole number (a count)."""
        self._add(
            ParamDef(
                name=name,
                label=label,
                description=description,
                kind=Kind.INTEGER,
                default=default,
                min=lo,
                max=hi,
                status=status,
            )
        )

    def flag(
        self,
        name: str,
        default: bool,
        label: str,
        description: str,
        status: Status = Status.DEFAULT,
    ) -> None:
        """Declare a yes/no switch."""
        self._add(
            ParamDef(
                name=name,
                label=label,
                description=description,
                kind=Kind.FLAG,
                default=default,
                status=status,
            )
        )

    def choice(
        self,
        name: str,
        default: str,
        choices: Sequence[str],
        label: str,
        description: str,
        status: Status = Status.DEFAULT,
    ) -> None:
        """Declare a pick-one-from-a-list value."""
        self._add(
            ParamDef(
                name=name,
                label=label,
                description=description,
                kind=Kind.CHOICE,
                default=default,
                choices=tuple(choices),
                status=status,
            )
        )

    def curve(
        self,
        name: str,
        default: Sequence[float],
        unit: str,
        lo: float,
        hi: float,
        label: str,
        description: str,
        status: Status = Status.DEFAULT,
    ) -> None:
        """Declare a list of numbers (one axis or the values of a lookup curve)."""
        self._add(
            ParamDef(
                name=name,
                label=label,
                description=description,
                kind=Kind.CURVE,
                default=units.list_to_si(default, unit),
                unit=unit,
                si_unit=units.si_unit(unit),
                min=units.to_si(lo, unit),
                max=units.to_si(hi, unit),
                status=status,
            )
        )

    # ---- looking parameters up ------------------------------------------------

    def get(self, name: str) -> ParamDef:
        """Return the definition of ``name`` or raise :class:`ParamError`."""
        try:
            return self._defs[name]
        except KeyError:
            hint = get_close_matches(name, self._defs.keys(), n=3)
            suffix = f" Did you mean: {', '.join(hint)}?" if hint else ""
            raise ParamError(f"Unknown parameter '{name}'.{suffix}") from None

    def __contains__(self, name: str) -> bool:
        return name in self._defs

    def __iter__(self) -> Iterator[ParamDef]:
        return iter(self._defs.values())

    def __len__(self) -> int:
        return len(self._defs)

    def names(self) -> list[str]:
        """All parameter names in declaration order."""
        return list(self._defs)

    def categories(self) -> dict[str, str]:
        """Category key -> title, in declaration order."""
        return dict(self._category_labels)

    def in_category(self, category: str) -> list[ParamDef]:
        """All definitions of one category, in declaration order."""
        return [d for d in self._defs.values() if d.category == category]

    # ---- validating values ------------------------------------------------------

    def validate(self, name: str, value: ParamValue) -> ParamValue:
        """Check an SI ``value`` against the definition; return the cleaned value."""
        d = self.get(name)
        if d.kind is Kind.FLAG:
            if not isinstance(value, bool):
                raise ParamError(f"{name}: expected yes/no, got {value!r}")
            return value
        if d.kind is Kind.CHOICE:
            if value not in d.choices:
                raise ParamError(f"{name}: '{value}' is not one of {list(d.choices)}")
            return value
        if d.kind is Kind.CURVE:
            if not isinstance(value, list) or len(value) < 2:
                raise ParamError(f"{name}: expected a list of at least 2 numbers")
            cleaned = [float(v) for v in value]
            for v in cleaned:
                self._check_range(d, v)
            return cleaned
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ParamError(f"{name}: expected a number, got {value!r}")
        if d.kind is Kind.INTEGER:
            if float(value) != int(value):
                raise ParamError(f"{name}: expected a whole number, got {value!r}")
            self._check_range(d, float(value))
            return int(value)
        self._check_range(d, float(value))
        return float(value)

    @staticmethod
    def _check_range(d: ParamDef, value: float) -> None:
        if value != value:  # NaN
            raise ParamError(f"{d.name}: value is not a number")
        tolerance = 1e-9 * max(1.0, abs(value))
        too_low = d.min is not None and value < d.min - tolerance
        too_high = d.max is not None and value > d.max + tolerance
        if too_low or too_high:
            lo = units.from_si(d.min, d.unit) if d.min is not None else float("-inf")
            hi = units.from_si(d.max, d.unit) if d.max is not None else float("inf")
            shown = units.from_si(value, d.unit)
            raise ParamError(
                f"{d.name}: {shown:g} {d.unit} is outside the allowed range "
                f"{lo:g} … {hi:g} {d.unit}"
            )
