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
