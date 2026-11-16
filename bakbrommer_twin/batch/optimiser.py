"""Optimiser: search parameter values (usually controller settings) for a goal.

Method: differential evolution (``scipy.optimize.differential_evolution``), a
robust global search that needs no gradients. Every candidate is a full
simulation. Hard safety constraints are enforced by ranking: any candidate
that breaks a constraint scores worse than every safe candidate, and among
unsafe ones the less severe is better — so the search is pulled back into the
safe region. The answer is the best *safe* candidate seen; if none was safe
the result says so.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field
from scipy.optimize import differential_evolution

from bakbrommer_twin.batch.constraints import SafetyConstraints
from bakbrommer_twin.batch.runner import Job, JobResult, run_jobs
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.types import Kind
from bakbrommer_twin.scenarios.scenario import Scenario

_UNSAFE_SCORE = 1e9  # added to every unsafe candidate so it ranks below all safe ones
OptimiserProgress = Callable[[int, float | None], None]  # (runs so far, best safe value)


class SearchParam(BaseModel):
    """One parameter the optimiser may change, with its search range (friendly units)."""

    param: str
    low: float
    high: float


class Goal(BaseModel):
    """What to optimise: a metric key (see the summary) and the direction."""

    metric: str
    direction: Literal["minimise", "maximise"] = "minimise"


class OptimiserSettings(BaseModel):
    """Size of the search. Runs ≈ population × parameters × (generations + 1)."""

    population: int = Field(default=5, ge=2, le=50)
    generations: int = Field(default=5, ge=1, le=200)
    seed: int = 1


@dataclass
class OptimiserResult:
    """Outcome of a search."""

    best: JobResult | None  # best safe candidate, None if no candidate was safe
    best_value: float | None  # its goal metric (SI)
    least_unsafe: JobResult | None  # shown when ``best`` is None
    history: list[JobResult]  # every candidate in the order it was run
    runs: int


def optimise(params: ParamSet, scenario: Scenario, search: list[SearchParam], goal: Goal,
             constraints: SafetyConstraints | None = None,
             settings: OptimiserSettings | None = None, workers: int = 1,
             progress: OptimiserProgress | None = None) -> OptimiserResult:
    """Search the ``search`` parameters for the best safe value of ``goal``."""
    limits = constraints or SafetyConstraints.from_params(params)
    config = settings or OptimiserSettings()
    if not search:
        raise ValueError("Choose at least one parameter to optimise")
    integer = []
    trial = params.copy()
    for item in search:
        definition = params.registry.get(item.param)
        if definition.kind not in (Kind.NUMBER, Kind.INTEGER):
            raise ValueError(f"'{item.param}' is not a number and cannot be optimised")
        if item.high <= item.low:
            raise ValueError(f"'{item.param}': the upper bound must be above the lower bound")
        integer.append(definition.kind is Kind.INTEGER)
        for bound in (item.low, item.high):  # raises if a bound is outside the allowed range
            trial.set_display(item.param, int(bound) if integer[-1] else bound)
    sign = 1.0 if goal.direction == "minimise" else -1.0
    history: list[JobResult] = []
    best: tuple[float, JobResult] | None = None
    least_unsafe: tuple[float, JobResult] | None = None

    def score(result: JobResult) -> float:
        nonlocal best, least_unsafe
        value = result.metrics.get(goal.metric)
        if result.error or value is None:
            return 2.0 * _UNSAFE_SCORE
        severity = limits.severity(result.metrics)
        if severity > 0.0:
            if least_unsafe is None or severity < least_unsafe[0]:
                least_unsafe = (severity, result)
            return _UNSAFE_SCORE * (1.0 + severity)
        if best is None or sign * value < best[0]:
            best = (sign * value, result)
        return sign * value

    def evaluate(_: object, candidates: Iterable[np.ndarray]) -> list[float]:
        """Run one generation of candidates (in parallel) and score them."""
        jobs = []
        for vector in candidates:
            overrides = {item.param: (round(float(x)) if whole else float(f"{float(x):.6g}"))
                         for item, x, whole in zip(search, vector, integer, strict=True)}
            jobs.append(Job(f"candidate {len(history) + len(jobs) + 1}", overrides))
        results = run_jobs(params, scenario, jobs, workers)
        scores = [score(result) for result in results]
        history.extend(results)
        if progress is not None:
            progress(len(history), None if best is None else sign * best[0])
        return scores

    differential_evolution(
        lambda _: 0.0, bounds=[(item.low, item.high) for item in search],
        maxiter=config.generations, popsize=config.population, seed=config.seed,
        polish=False, tol=0.0, atol=0.0, updating="deferred", workers=evaluate)
    if goal.metric not in (history[0].metrics if history else {}):
        raise ValueError(f"The scenario does not produce a metric called '{goal.metric}'")
    return OptimiserResult(
        best=None if best is None else best[1],
        best_value=None if best is None else sign * best[0],
        least_unsafe=None if least_unsafe is None else least_unsafe[1],
        history=history, runs=len(history))
