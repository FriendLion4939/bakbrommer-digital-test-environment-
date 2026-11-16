"""Parameter sweeps: run a scenario for every value (or pair of values) on a grid."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bakbrommer_twin.batch.constraints import SafetyConstraints
from bakbrommer_twin.batch.runner import Job, ProgressCallback, run_jobs
from bakbrommer_twin.batch.tables import results_table
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.types import Kind
from bakbrommer_twin.scenarios.scenario import Scenario


@dataclass(frozen=True)
class SweepAxis:
    """One swept parameter and the values to try (friendly units)."""

    param: str
    values: list[float]


def linear_values(start: float, stop: float, count: int) -> list[float]:
    """``count`` evenly spaced values from ``start`` to ``stop`` (both included)."""
    return [float(f"{v:.9g}") for v in np.linspace(start, stop, max(2, count))]


def sweep_jobs(first: SweepAxis, second: SweepAxis | None = None) -> list[Job]:
    """All jobs of a one- or two-parameter sweep."""
    jobs = []
    for a in first.values:
        if second is None:
            jobs.append(Job(f"{first.param}={a:g}", {first.param: a}))
        else:
            for b in second.values:
                jobs.append(Job(f"{first.param}={a:g}, {second.param}={b:g}",
                                {first.param: a, second.param: b}))
    return jobs


def check_axis(params: ParamSet, axis: SweepAxis) -> None:
    """Raise ``ValueError`` if the axis names a non-numeric parameter or a value out of range."""
    definition = params.registry.get(axis.param)
    if definition.kind not in (Kind.NUMBER, Kind.INTEGER):
        raise ValueError(f"'{axis.param}' is not a number and cannot be swept")
    trial = params.copy()
    for value in axis.values:
        trial.set_display(axis.param, int(value) if definition.kind is Kind.INTEGER else value)


def run_sweep(params: ParamSet, scenario: Scenario, first: SweepAxis,
              second: SweepAxis | None = None, constraints: SafetyConstraints | None = None,
              workers: int = 1, progress: ProgressCallback | None = None) -> pd.DataFrame:
    """Run the sweep and return one table row per grid point."""
    for axis in (first, second):
        if axis is not None:
            check_axis(params, axis)
    results = run_jobs(params, scenario, sweep_jobs(first, second), workers, progress)
    return results_table(results, constraints or SafetyConstraints.from_params(params))
