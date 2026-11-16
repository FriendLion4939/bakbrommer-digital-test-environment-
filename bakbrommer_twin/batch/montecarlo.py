"""Monte Carlo: many runs with random variation of chosen parameters.

Each run draws every varied parameter from a distribution around its profile
value and uses its own random seed (so sensor noise and road bumps differ
too). The result shows how much the outcome scatters and how often a safety
constraint is broken.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from bakbrommer_twin.batch.constraints import SafetyConstraints
from bakbrommer_twin.batch.runner import Job, ProgressCallback, run_jobs
from bakbrommer_twin.batch.tables import results_table
from bakbrommer_twin.params import units
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.types import Kind
from bakbrommer_twin.scenarios.scenario import Scenario

SEED_PARAM = "sim.random_seed"


class Variation(BaseModel):
    """How one parameter is varied."""

    param: str
    spread: float = Field(gt=0)  # standard deviation (normal) or half-width (uniform)
    relative: bool = True  # True: spread is a fraction of the value; False: friendly units
    distribution: Literal["normal", "uniform"] = "normal"


def monte_carlo_jobs(params: ParamSet, variations: list[Variation], count: int,
                     seed: int) -> list[Job]:
    """Draw ``count`` random parameter sets (reproducible for a given ``seed``)."""
    rng = np.random.default_rng(seed)
    jobs = []
    for index in range(count):
        overrides: dict[str, float | int | bool | str | list[float]] = {
            SEED_PARAM: int(rng.integers(0, 1_000_000))}
        for variation in variations:
            definition = params.registry.get(variation.param)
            if definition.kind is not Kind.NUMBER:
                raise ValueError(f"'{variation.param}' is not a number and cannot be varied")
            centre = float(params.display(variation.param))  # type: ignore[arg-type]
            width = variation.spread * abs(centre) if variation.relative else variation.spread
            if variation.distribution == "normal":
                value = rng.normal(centre, width)
            else:
                value = rng.uniform(centre - width, centre + width)
            low = units.from_si(definition.min or 0.0, definition.unit)
            high = units.from_si(definition.max or 0.0, definition.unit)
            overrides[variation.param] = float(min(high, max(low, value)))
        jobs.append(Job(f"sample {index + 1}", overrides))
    return jobs


def run_monte_carlo(params: ParamSet, scenario: Scenario, variations: list[Variation],
                    count: int, seed: int = 1, constraints: SafetyConstraints | None = None,
                    workers: int = 1, progress: ProgressCallback | None = None) -> pd.DataFrame:
    """Run the samples and return one table row per sample."""
    jobs = monte_carlo_jobs(params, variations, count, seed)
    results = run_jobs(params, scenario, jobs, workers, progress)
    return results_table(results, constraints or SafetyConstraints.from_params(params))


def statistics(table: pd.DataFrame) -> pd.DataFrame:
    """Mean, spread and percentiles of every numeric column of a results table."""
    numeric = table.select_dtypes("number").drop(columns=[SEED_PARAM], errors="ignore")
    stats = numeric.describe(percentiles=[0.05, 0.5, 0.95]).T
    return stats[["mean", "std", "min", "5%", "50%", "95%", "max"]]


def unsafe_share(table: pd.DataFrame) -> float:
    """Fraction of the samples that broke a safety constraint (0…1)."""
    return float(1.0 - table["safe"].mean()) if len(table) else 0.0
