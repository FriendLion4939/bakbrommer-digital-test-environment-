"""Turns batch results into tables (pandas) for the UI and for export."""

from __future__ import annotations

import pandas as pd

from bakbrommer_twin.batch.constraints import SafetyConstraints
from bakbrommer_twin.batch.runner import JobResult
from bakbrommer_twin.params import units


def metric_column(key: str, unit: str) -> str:
    """Column title of a metric: ``key [unit]`` (or just the key when unit-less)."""
    return key if unit in ("", "-") else f"{key} [{unit}]"


def results_table(results: list[JobResult], constraints: SafetyConstraints) -> pd.DataFrame:
    """One row per run: changed parameters, end reason, safety verdict, all metrics.

    Parameter columns hold the values as given (friendly units); metric columns
    are converted to their friendly units.
    """
    rows = []
    for result in results:
        row: dict[str, object] = {"run": result.label}
        row.update(result.overrides)
        row["end_reason"] = result.end_reason if not result.error else f"error: {result.error}"
        broken = constraints.violations(result.metrics) if not result.error else ["not run"]
        row["safe"] = not broken
        row["violations"] = "; ".join(broken)
        for key, value in result.metrics.items():
            unit = result.metric_units[key]
            row[metric_column(key, unit)] = (
                None if value is None else units.from_si(value, unit))
        rows.append(row)
    return pd.DataFrame(rows)


def metric_choices(results: list[JobResult]) -> dict[str, str]:
    """Column title → readable label, for metric pickers in the UI."""
    choices: dict[str, str] = {}
    for result in results:
        for key, unit in result.metric_units.items():
            choices.setdefault(metric_column(key, unit), result.metric_labels[key])
    return choices
