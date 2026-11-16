"""Batch tools: runner, sweeps, Monte Carlo, optimiser, safety constraints."""

import pytest
from helpers import scenario, straight

from bakbrommer_twin.batch.constraints import SafetyConstraints
from bakbrommer_twin.batch.montecarlo import (
    Variation,
    monte_carlo_jobs,
    run_monte_carlo,
    statistics,
    unsafe_share,
)
from bakbrommer_twin.batch.optimiser import Goal, OptimiserSettings, SearchParam, optimise
from bakbrommer_twin.batch.runner import Job, run_jobs
from bakbrommer_twin.batch.sweep import SweepAxis, linear_values, run_sweep, sweep_jobs
from bakbrommer_twin.batch.tables import metric_choices
from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.scenarios.scenario import Scenario


@pytest.fixture
def sprint() -> Scenario:
    return scenario([straight(400, throttle=1.0)], end={"time_limit_s": 15, "at_speed_kmh": 25},
                    metrics=[{"type": "time_to_speed", "speed_kmh": 25}])


def test_run_jobs_keeps_order_and_matches_parallel(params: ParamSet, sprint: Scenario) -> None:
    jobs = [Job("light", {"mass.cargo.mass": 0}), Job("heavy", {"mass.cargo.mass": 100}),
            Job("medium", {"mass.cargo.mass": 50})]
    serial = run_jobs(params, sprint, jobs)
    calls: list[tuple[int, int]] = []
    parallel = run_jobs(params, sprint, jobs, workers=2,
                        progress=lambda done, total: calls.append((done, total)))
    assert [r.label for r in serial] == ["light", "heavy", "medium"]
    assert [r.metrics["time_0_25"] for r in serial] == [r.metrics["time_0_25"] for r in parallel]
    assert serial[0].metrics["time_0_25"] < serial[2].metrics["time_0_25"] < serial[1].metrics[
        "time_0_25"]
    assert calls[-1] == (3, 3)
    assert serial[0].metric_units["time_0_25"] == "s"


def test_invalid_job_is_reported_not_raised(params: ParamSet, sprint: Scenario) -> None:
    (result,) = run_jobs(params, sprint, [Job("bad", {"mass.cargo.mass": -5})])
    assert result.end_reason == "error" and "outside the allowed range" in result.error


def test_sweep_grid_and_table(params: ParamSet, sprint: Scenario) -> None:
    assert linear_values(0, 100, 3) == [0.0, 50.0, 100.0]
    axis_a = SweepAxis("mass.cargo.mass", [0.0, 100.0])
    axis_b = SweepAxis("control.mode_normal.electric_torque", [20.0, 45.0])
    assert len(sweep_jobs(axis_a, axis_b)) == 4
    table = run_sweep(params, sprint, axis_a, axis_b)
    assert len(table) == 4
    assert {"mass.cargo.mass", "control.mode_normal.electric_torque", "safe", "violations",
            "time_0_25 [s]", "max_speed [km/h]"} <= set(table.columns)
    quickest = table.sort_values("time_0_25 [s]").iloc[0]
    assert quickest["mass.cargo.mass"] == 0.0
    assert quickest["control.mode_normal.electric_torque"] == 45.0
    assert table["max_speed [km/h]"].max() == pytest.approx(25.0, abs=0.5)


def test_sweep_rejects_bad_axes(params: ParamSet, sprint: Scenario) -> None:
    with pytest.raises(ValueError, match="cannot be swept"):
        run_sweep(params, sprint, SweepAxis("steering.type", [1.0]))
    with pytest.raises(ValueError, match="outside the allowed range"):
        run_sweep(params, sprint, SweepAxis("mass.cargo.mass", [0.0, 9999.0]))


def test_monte_carlo_is_reproducible_and_varies(params: ParamSet, sprint: Scenario) -> None:
    variations = [Variation(param="mass.cargo.mass", spread=20.0, relative=False),
                  Variation(param="surface.dry_asphalt.friction", spread=0.1,
                            distribution="uniform")]
    first = monte_carlo_jobs(params, variations, 5, seed=3)
    assert first == monte_carlo_jobs(params, variations, 5, seed=3)
    assert first != monte_carlo_jobs(params, variations, 5, seed=4)
    masses = [job.overrides["mass.cargo.mass"] for job in first]
    assert min(masses) >= 0.0  # clipped to the allowed range (cargo cannot be negative)
    frictions = [job.overrides["surface.dry_asphalt.friction"] for job in first]
    assert all(0.855 - 1e-9 <= f <= 1.045 + 1e-9 for f in frictions)  # 0.95 ± 10 %
    table = run_monte_carlo(params, sprint, variations, 5, seed=3)
    assert len(table) == 5 and table["time_0_25 [s]"].std() > 0.0
    stats = statistics(table)
    assert stats.loc["time_0_25 [s]", "min"] <= stats.loc["time_0_25 [s]", "50%"] <= stats.loc[
        "time_0_25 [s]", "max"]
    assert 0.0 <= unsafe_share(table) <= 1.0


def test_constraints_list_what_was_broken(params: ParamSet) -> None:
    limits = SafetyConstraints.from_params(params)
    assert limits.max_battery_current == pytest.approx(35.0)
    safe = {"rolled_over": 0.0, "wheel_lift_events": 0.0, "max_wheel_lift": 0.0,
            "peak_battery_current": 30.0, "max_motor_temp": 60.0, "bms_trips": 0.0,
            "min_rollover_margin": 0.4}
    assert limits.violations(safe) == [] and limits.severity(safe) == 0.0
    bad = dict(safe, rolled_over=1.0, peak_battery_current=50.0, wheel_lift_events=2.0)
    broken = limits.violations(bad)
    assert len(broken) == 3 and "rolled over" in broken
    assert limits.severity(bad) > limits.severity(dict(safe, peak_battery_current=50.0)) > 0.0
    relaxed = SafetyConstraints(max_wheel_lift_events=3, max_battery_current=60.0,
                                allow_rollover=True)
    assert relaxed.violations(bad) == []


def test_optimiser_finds_the_best_safe_setting(params: ParamSet, sprint: Scenario) -> None:
    # More motor torque is always quicker, but the battery current may not exceed 20 A:
    # the optimum is the largest torque that just respects the limit.
    params.set_display("motor.line_current_limit", 40.0)
    params.set_display("control.limits.battery_current", 60.0)
    limits = SafetyConstraints(max_battery_current=20.0)
    result = optimise(
        params, sprint, [SearchParam(param="control.mode_normal.electric_torque", low=5, high=80)],
        Goal(metric="time_0_25"), limits, OptimiserSettings(population=6, generations=4, seed=2))
    assert result.runs == 6 * 5
    assert result.best is not None and result.best_value is not None
    assert result.best.metrics["peak_battery_current"] <= 20.0
    unsafe = [r for r in result.history if limits.violations(r.metrics)]
    assert unsafe, "the search should have tried torques that are too high"
    safe_times = [r.metrics["time_0_25"] for r in result.history
                  if not limits.violations(r.metrics) and r.metrics["time_0_25"] is not None]
    assert result.best_value == pytest.approx(min(safe_times))
    assert metric_choices(result.history)["time_0_25 [s]"].startswith("Time")


def test_optimiser_reports_when_nothing_is_safe(params: ParamSet, sprint: Scenario) -> None:
    impossible = SafetyConstraints(max_battery_current=0.5)
    result = optimise(
        params, sprint, [SearchParam(param="control.mode_normal.electric_torque", low=20, high=60)],
        Goal(metric="time_0_25"), impossible, OptimiserSettings(population=2, generations=1))
    assert result.best is None and result.least_unsafe is not None


def test_optimiser_checks_its_inputs(params: ParamSet, sprint: Scenario) -> None:
    with pytest.raises(ValueError, match="at least one"):
        optimise(params, sprint, [], Goal(metric="time_0_25"))
    with pytest.raises(ValueError, match="upper bound"):
        optimise(params, sprint, [SearchParam(param="mass.cargo.mass", low=5, high=5)],
                 Goal(metric="time_0_25"))
    with pytest.raises(ValueError, match="does not produce"):
        optimise(params, sprint, [SearchParam(param="mass.cargo.mass", low=0, high=5)],
                 Goal(metric="lap_record"), settings=OptimiserSettings(population=2,
                                                                       generations=1))
