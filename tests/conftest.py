"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bakbrommer_twin import paths
from bakbrommer_twin.params import REGISTRY, ParamSet, default_params
from bakbrommer_twin.params.profile import ProfileStore


@pytest.fixture
def params() -> ParamSet:
    """Registry defaults."""
    return default_params()


@pytest.fixture
def store(tmp_path: Path) -> ProfileStore:
    """A profile store in a temporary folder, pre-filled with the shipped profiles."""
    target = tmp_path / "profiles"
    target.mkdir()
    for source in (paths.PROJECT_ROOT / "data" / "profiles").glob("*.yaml"):
        shutil.copy(source, target / source.name)
    return ProfileStore(target, REGISTRY)


@pytest.fixture
def quiet(params: ParamSet) -> ParamSet:
    """Defaults with ideal sensors, direct controller, no BMS trip: the physics alone."""
    params.set("sensors.ideal", True)
    params.set("control.controller_type", "direct")
    params.set("battery.bms_trip_enabled", False)
    return params
