"""Runs many simulations, in parallel worker processes when asked.

A :class:`Job` is "this scenario with these parameter changes". Workers get
plain dictionaries (they must be sent between processes) and return a
:class:`JobResult` with the run's numbers — not the recorded signals, which
would be too much data for hundreds of runs.
"""

from __future__ import annotations

import multiprocessing
import os
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field

from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.types import ParamValue
from bakbrommer_twin.scenarios.scenario import Scenario
from bakbrommer_twin.sim.simulator import run_scenario

ProgressCallback = Callable[[int, int], None]  # (finished, total)
ParamDict = dict[str, ParamValue]


@dataclass(frozen=True)
class Job:
    """One simulation to run: a label and parameter changes (friendly units)."""

    label: str
    overrides: ParamDict = field(default_factory=dict)


@dataclass(frozen=True)
class JobResult:
    """The numbers of one finished run (SI units)."""

    label: str
    overrides: ParamDict
    end_reason: str
    metrics: dict[str, float | None]  # summary and scenario metrics by key
    metric_units: dict[str, str]  # friendly unit of each metric
    metric_labels: dict[str, str]  # readable name of each metric
    event_counts: dict[str, int]  # safety events by kind
    error: str = ""  # set when the run could not be carried out


def default_workers() -> int:
    """A sensible number of worker processes for this machine."""
    return max(1, (os.cpu_count() or 2) - 1)


def run_job(base: ParamDict, scenario: dict[str, object], job: Job) -> JobResult:
    """Run one job (this function is what worker processes execute)."""
    try:
        params = ParamSet.from_display_dict(REGISTRY, base).with_display_overrides(job.overrides)
        result = run_scenario(params, Scenario.model_validate(scenario))
    except (ValueError, ArithmeticError) as exc:  # invalid combination of parameters
        return JobResult(job.label, job.overrides, "error", {}, {}, {}, {}, error=str(exc))
    found = (*result.meta.summary, *result.meta.metrics)
    metrics = {m.key: m.value for m in found}
    counts: dict[str, int] = {}
    for event in result.meta.events:
        counts[event.kind] = counts.get(event.kind, 0) + 1
    return JobResult(job.label, job.overrides, result.meta.end_reason, metrics,
                     {m.key: m.unit for m in found}, {m.key: m.label for m in found}, counts)


def run_jobs(params: ParamSet, scenario: Scenario, jobs: Iterable[Job], workers: int = 1,
             progress: ProgressCallback | None = None) -> list[JobResult]:
    """Run all jobs and return their results in the order of ``jobs``."""
    job_list = list(jobs)
    base = params.as_display_dict()
    scenario_dict = scenario.model_dump(mode="json")
    results: list[JobResult | None] = [None] * len(job_list)
    if workers <= 1 or len(job_list) <= 1:
        for index, job in enumerate(job_list):
            results[index] = run_job(base, scenario_dict, job)
            if progress is not None:
                progress(index + 1, len(job_list))
    else:
        # "spawn" starts clean worker processes; forking a multi-threaded web server is unsafe.
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            futures = {pool.submit(run_job, base, scenario_dict, job): index
                       for index, job in enumerate(job_list)}
            for done, future in enumerate(as_completed(futures), start=1):
                results[futures[future]] = future.result()
                if progress is not None:
                    progress(done, len(job_list))
    return [result for result in results if result is not None]
