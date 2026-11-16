"""Regression test: every shipped scenario must reproduce its reference numbers.

A failure here means behaviour changed. If the change is intended, run
``python scripts/update_reference.py`` and review the diff of
``tests/reference/scenarios.yaml``.
"""

from typing import Any

import pytest
import reference_tools
import yaml

RELATIVE_TOLERANCE = 0.02
ABSOLUTE_TOLERANCE = 1e-3


def _reference() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(
        reference_tools.REFERENCE_FILE.read_text(encoding="utf-8"))
    return loaded


def test_reference_covers_exactly_the_shipped_scenarios() -> None:
    assert sorted(_reference()) == reference_tools.scenario_keys(), (
        "run python scripts/update_reference.py")


@pytest.mark.parametrize("key", reference_tools.scenario_keys())
def test_scenario_matches_reference(key: str) -> None:
    expected = _reference()[key]
    actual = reference_tools.collect(key)
    assert actual["end_reason"] == expected["end_reason"]
    values: dict[str, float | None] = actual["values"]  # type: ignore[assignment]
    assert set(values) == set(expected["values"])
    for name, reference in expected["values"].items():
        if reference is None:
            assert values[name] is None, name
        else:
            assert values[name] == pytest.approx(
                reference, rel=RELATIVE_TOLERANCE, abs=ABSOLUTE_TOLERANCE), name
