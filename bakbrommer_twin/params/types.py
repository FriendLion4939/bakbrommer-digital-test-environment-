"""Data types of the parameter registry."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

# A parameter value in SI units: number, yes/no, choice text, or curve.
ParamValue = float | int | bool | str | list[float]


class Status(StrEnum):
    """How trustworthy a parameter value is."""

    MEASURED = "measured"  # measured on the real vehicle or given by the builder
    ESTIMATED = "estimated"  # educated estimate from datasheets / similar parts
    DEFAULT = "default"  # generic placeholder value — needs measuring
    CALIBRATED = "calibrated"  # fitted to a real log by the calibration tool


class Kind(StrEnum):
    """What sort of value a parameter holds (decides the UI widget)."""

    NUMBER = "number"
    INTEGER = "integer"
    FLAG = "flag"
    CHOICE = "choice"
    CURVE = "curve"


class ParamDef(BaseModel):
    """Definition of one parameter. Values (default, min, max) are stored in SI."""

    model_config = ConfigDict(frozen=True)

    name: str  # dotted name, e.g. "battery.internal_resistance"
    label: str  # short human-readable name
    description: str
    kind: Kind
    default: ParamValue  # SI
    unit: str = ""  # friendly unit used in the UI and in YAML files
    si_unit: str = ""  # unit used inside the code
    min: float | None = None  # SI
    max: float | None = None  # SI
    status: Status = Status.DEFAULT
    choices: tuple[str, ...] = ()

    @property
    def category(self) -> str:
        """First part of the dotted name; one tab in the UI."""
        return self.name.split(".")[0]

    @property
    def group(self) -> str:
        """Second part of a three-part name (sub-heading in the UI), else ''."""
        parts = self.name.split(".")
        return parts[1] if len(parts) >= 3 else ""

    @model_validator(mode="after")
    def _check(self) -> ParamDef:
        if not self.name or " " in self.name or "." not in self.name:
            raise ValueError(f"Parameter name '{self.name}' must be dotted, e.g. 'tyre.radius'")
        if self.kind is Kind.CHOICE and self.default not in self.choices:
            raise ValueError(f"{self.name}: default '{self.default}' is not one of {self.choices}")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"{self.name}: min is larger than max")
        return self


class ParamError(ValueError):
    """Raised for an unknown parameter name or an invalid value."""
