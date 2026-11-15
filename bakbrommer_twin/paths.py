"""Where the program keeps its files.

``data/`` holds things the user edits (profiles, scenarios, CAN definitions,
mappings, example logs). ``runs/`` holds saved simulation results. Both can be
moved with the environment variables below (Docker uses this for volumes).
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ENV_DATA_DIR = "BAKBROMMER_DATA_DIR"
ENV_RUNS_DIR = "BAKBROMMER_RUNS_DIR"


def data_dir() -> Path:
    """Folder with profiles, scenarios, CAN definitions, mappings and example logs."""
    return Path(os.environ.get(ENV_DATA_DIR, PROJECT_ROOT / "data"))


def runs_dir() -> Path:
    """Folder where simulation results are saved (created when missing)."""
    path = Path(os.environ.get(ENV_RUNS_DIR, PROJECT_ROOT / "runs"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def profiles_dir() -> Path:
    """Folder with vehicle profiles (YAML)."""
    return data_dir() / "profiles"


def scenarios_dir() -> Path:
    """Folder with scenario files (YAML)."""
    return data_dir() / "scenarios"
