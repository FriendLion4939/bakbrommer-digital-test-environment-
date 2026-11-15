"""Vehicle profiles: named parameter sets stored as human-readable YAML.

A profile file lists only the values that differ from its ``base`` profile
(or from the registry defaults when it has no base)::

    name: Full cargo
    description: Bike loaded with 80 kg in the box
    base: default
    validated: false
    values:
      mass.cargo.mass: {value: 80, unit: kg, status: estimated, note: 8 crates}
      mass.cargo.height: 0.65        # short form: number in the parameter's unit

Every save also writes a time-stamped copy to ``.history/<key>/`` so earlier
versions can be compared and restored.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from bakbrommer_twin.params import units
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Kind, ParamError, ParamValue, Status

HISTORY_DIR = ".history"
_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


class ProfileEntry(BaseModel):
    """One value in a profile file (long form)."""

    model_config = ConfigDict(extra="forbid")

    value: ParamValue
    unit: str | None = None
    status: Status | None = None
    note: str = ""


class ProfileFile(BaseModel):
    """Schema of a profile YAML file."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    base: str | None = None
    validated: bool = False
    values: dict[str, ProfileEntry | ParamValue] = {}


@dataclass
class Profile:
    """A profile in memory: metadata plus the fully resolved parameter set."""

    key: str  # file name without .yaml
    name: str
    params: ParamSet
    description: str = ""
    base: str | None = None
    validated: bool = False  # True once calibrated against real data
    notes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DiffRow:
    """One differing parameter in a side-by-side comparison (friendly units)."""

    name: str
    label: str
    unit: str
    value_a: ParamValue
    value_b: ParamValue
    status_a: Status
    status_b: Status


def compare(a: ParamSet, b: ParamSet) -> list[DiffRow]:
    """List every parameter whose value or status differs between two sets."""
    rows = []
    for name in a.differences(b):
        d = a.registry.get(name)
        rows.append(
            DiffRow(name, d.label, d.unit, a.display(name), b.display(name),
                    a.status(name), b.status(name))
        )
    return rows


def _tidy(value: ParamValue) -> ParamValue:
    """Round away floating-point dust so YAML files stay readable."""
    if isinstance(value, bool | str | int):
        return value
    if isinstance(value, list):
        return [float(f"{v:.9g}") for v in value]
    return float(f"{value:.9g}")


def _entry_to_si(registry: Registry, name: str, entry: ProfileEntry) -> ParamValue:
    """Convert a file entry to an SI value, honouring an explicit unit."""
    d = registry.get(name)
    unit = entry.unit if entry.unit is not None else d.unit
    if d.kind in (Kind.NUMBER, Kind.CURVE) and units.si_unit(unit) != d.si_unit:
        raise ParamError(f"{name}: unit '{unit}' does not fit; expected something like '{d.unit}'")
    value = entry.value
    if d.kind is Kind.NUMBER and isinstance(value, int | float) and not isinstance(value, bool):
        return units.to_si(float(value), unit)
    if d.kind is Kind.CURVE and isinstance(value, list):
        return units.list_to_si(value, unit)
    return value


class ProfileStore:
    """Loads and saves profiles in one folder."""

    def __init__(self, directory: Path, registry: Registry) -> None:
        self.directory = directory
        self.registry = registry

    def _path(self, key: str) -> Path:
        if not _KEY_PATTERN.match(key):
            raise ParamError(
                f"Profile file name '{key}' may only contain lower-case letters, digits, _ and -"
            )
        return self.directory / f"{key}.yaml"

    def list_keys(self) -> list[str]:
        """Names (file stems) of all profiles in the folder, sorted."""
        return sorted(p.stem for p in self.directory.glob("*.yaml"))

    def exists(self, key: str) -> bool:
        """True when a profile file with this key exists."""
        return self._path(key).exists()

    # ---- loading ------------------------------------------------------------------

    def load(self, key: str) -> Profile:
        """Load a profile and everything it inherits from its base profiles."""
        return self._load_path(key, self._path(key), chain=(key,))

    def _load_path(self, key: str, path: Path, chain: tuple[str, ...]) -> Profile:
        if not path.exists():
            raise ParamError(f"Profile '{key}' not found in {self.directory}")
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        data = ProfileFile.model_validate(raw)
        if data.base is None:
            params = ParamSet(self.registry)
        else:
            if data.base in chain:
                raise ParamError(f"Profiles inherit in a circle: {' → '.join(chain)} → {data.base}")
            base_chain = (*chain, data.base)
            params = self._load_path(data.base, self._path(data.base), base_chain).params
        notes: dict[str, str] = {}
        for name, raw_entry in data.values.items():
            entry = raw_entry if isinstance(raw_entry, ProfileEntry) else ProfileEntry(
                value=raw_entry)
            try:
                params.set(name, _entry_to_si(self.registry, name, entry), entry.status)
            except (ParamError, units.UnknownUnitError) as exc:
                raise ParamError(f"Profile '{key}': {exc}") from exc
            if entry.note:
                notes[name] = entry.note
        return Profile(key, data.name, params, data.description, data.base, data.validated, notes)

    # ---- saving -------------------------------------------------------------------

    def _to_file(self, profile: Profile) -> ProfileFile:
        base_params = (
            self.load(profile.base).params if profile.base else ParamSet(self.registry)
        )
        values: dict[str, ProfileEntry | ParamValue] = {}
        for name in base_params.differences(profile.params):
            values[name] = ProfileEntry(
                value=_tidy(profile.params.display(name)),
                unit=self.registry.get(name).unit or None,
                status=profile.params.status(name),
                note=profile.notes.get(name, ""),
            )
        return ProfileFile(
            name=profile.name,
            description=profile.description,
            base=profile.base,
            validated=profile.validated,
            values=values,
        )

    def save(self, profile: Profile) -> Path:
        """Write the profile and add a time-stamped copy to its history."""
        if profile.base == profile.key:
            raise ParamError("A profile cannot be its own base")
        path = self._path(profile.key)
        data = self._to_file(profile).model_dump(mode="json", exclude_defaults=False)
        for entry in data["values"].values():
            if not entry["note"]:
                del entry["note"]
            if entry["unit"] is None:
                del entry["unit"]
        self.directory.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        path.write_text(text, encoding="utf-8")
        history = self.directory / HISTORY_DIR / profile.key
        history.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        (history / f"{stamp}.yaml").write_text(text, encoding="utf-8")
        return path

    def copy(self, key: str, new_key: str, new_name: str) -> Profile:
        """Duplicate a profile under a new key and name."""
        if self.exists(new_key):
            raise ParamError(f"Profile '{new_key}' already exists")
        source = self.load(key)
        duplicate = Profile(new_key, new_name, source.params.copy(), source.description,
                            source.base, source.validated, dict(source.notes))
        self.save(duplicate)
        return duplicate

    def delete(self, key: str) -> None:
        """Remove a profile and its history. Refuses when other profiles build on it."""
        dependants = [k for k in self.list_keys() if k != key and self._base_of(k) == key]
        if dependants:
            raise ParamError(f"Cannot delete '{key}': it is the base of {', '.join(dependants)}")
        self._path(key).unlink()
        shutil.rmtree(self.directory / HISTORY_DIR / key, ignore_errors=True)

    def _base_of(self, key: str) -> str | None:
        raw: Any = yaml.safe_load(self._path(key).read_text(encoding="utf-8"))
        return raw.get("base") if isinstance(raw, dict) else None

    # ---- history ------------------------------------------------------------------

    def history(self, key: str) -> list[str]:
        """Time stamps of the saved versions of a profile, newest first."""
        folder = self.directory / HISTORY_DIR / key
        return sorted((p.stem for p in folder.glob("*.yaml")), reverse=True)

    def load_version(self, key: str, stamp: str) -> Profile:
        """Load one saved version from the history of a profile."""
        path = self.directory / HISTORY_DIR / key / f"{stamp}.yaml"
        return self._load_path(key, path, chain=(key,))
