"""The documentation must stay in step with the code."""

from __future__ import annotations

import re

from bakbrommer_twin import paths
from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.definitions.control import CONTROLLER_TYPES, RIDE_MODES
from bakbrommer_twin.reports.curve_figures import CURVES

ROOT = paths.PROJECT_ROOT
DOCS = [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "docs").glob("*.md"))]
PACKAGE = ROOT / "bakbrommer_twin"
# docs that describe history or plans may mention files that no longer exist
HISTORICAL = {"PLAN.md", "PROGRESS.md"}


def _architecture() -> str:
    return (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")


def test_architecture_mentions_every_module() -> None:
    text = _architecture()
    missing = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE)
        if path.name == "__init__.py" or (relative.parts[0] == "params" and (
                "definitions" in relative.parts)):
            continue  # packages and the per-category definition files are described as groups
        if relative.parts[:2] == ("control", "reference"):
            continue  # described in docs/CONTROLLER.md
        if path.name not in text:
            missing.append(str(relative))
    assert not missing, f"describe these modules in docs/ARCHITECTURE.md: {missing}"


def test_controller_doc_mentions_every_block_and_type() -> None:
    text = (ROOT / "docs" / "CONTROLLER.md").read_text(encoding="utf-8")
    for path in (PACKAGE / "control" / "reference").glob("*.py"):
        assert path.name == "__init__.py" or path.name in text, path.name
    for name in CONTROLLER_TYPES:
        assert f"`{name}`" in text, name
    assert len(RIDE_MODES) == 4, "a ride mode was added: update the table in CONTROLLER.md"


def test_paths_named_in_the_docs_exist() -> None:
    pattern = re.compile(r"`((?:bakbrommer_twin|data|docs|scripts|tests)/[\w./\-]+)`")
    broken = []
    for doc in DOCS:
        if doc.name in HISTORICAL:
            continue
        for found in pattern.findall(doc.read_text(encoding="utf-8")):
            target = found.rstrip("/.")
            if "<" in target or "*" in target or (ROOT / target).exists():
                continue
            broken.append(f"{doc.name}: {found}")
    assert not broken, f"these paths in the docs do not exist: {broken}"


def test_parameters_named_in_the_docs_exist() -> None:
    pattern = re.compile(r"`([a-z_]+\.[a-z_0-9]+(?:\.[a-z_0-9]+)?)`")
    categories = set(REGISTRY.categories())
    unknown = []
    for doc in DOCS:
        if doc.name in HISTORICAL:
            continue
        for found in pattern.findall(doc.read_text(encoding="utf-8")):
            if found.endswith((".py", ".yaml", ".md", ".h", ".c", ".sh")):
                continue  # a file name, not a parameter
            if found.split(".")[0] in categories and found not in REGISTRY:
                unknown.append(f"{doc.name}: {found}")
    assert not unknown, f"the docs name parameters that do not exist: {unknown}"


def test_readme_names_what_the_ui_offers() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for needed in ("start.bat", "./start.sh", "docker compose up", "NOT VALIDATED",
                   "synthetic", "Run a simulation", "Import and replay a ride", "Calibration",
                   "Sweeps and optimiser", "Curves"):
        assert needed in readme, needed
    assert len(CURVES) == 4
