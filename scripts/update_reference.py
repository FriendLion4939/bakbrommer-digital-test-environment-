"""Regenerate tests/reference/scenarios.yaml from the current program.

Run this only after an intended change of behaviour, then look at
``git diff tests/reference`` and make sure every changed number makes sense.

Usage:  python scripts/update_reference.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

import reference_tools


def main() -> None:
    """Run all shipped scenarios and write their reference numbers."""
    data = {key: reference_tools.collect(key) for key in reference_tools.scenario_keys()}
    reference_tools.REFERENCE_FILE.write_text(
        yaml.safe_dump(data, sort_keys=True, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {len(data)} scenarios to {reference_tools.REFERENCE_FILE}")


if __name__ == "__main__":
    main()
