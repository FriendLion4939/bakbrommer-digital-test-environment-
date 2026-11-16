"""Calibration: adjust chosen parameters until a replay matches the measurement.

Method: non-linear least squares (``scipy.optimize.least_squares``, trust
region, bounded by each parameter's allowed range). The residual is, for
every chosen measured channel, (simulated − measured) divided by the standard
deviation of the measurement, so channels with different units weigh the
same. Every evaluation is one replay of the recording with ideal simulated
sensors (the measurement already contains the real sensor noise).

A good fit does not prove the model: parameters can compensate for each
other (e.g. mass and rolling resistance on a flat road). Fit few parameters
at a time, with a ride that excites them (coast-down for drag and rolling
resistance, hard acceleration for mass, long pulls for battery resistance).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from bakbrommer_twin.data_import.channels import LOG_CHANNELS
from bakbrommer_twin.data_import.recording import Recording
from bakbrommer_twin.data_import.replay import MEASURED_PREFIX, FitQuality, fit_quality, replay
from bakbrommer_twin.params import units
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.profile import Profile
from bakbrommer_twin.params.types import Kind, Status

# Parameters offered first in the UI (the usual suspects).
SUGGESTED_PARAMS: tuple[str, ...] = (
    "mass.chassis.mass", "tyre.rolling_resistance_scale", "aero.frontal_area",
    "surface.dry_asphalt.friction", "motor.phase_resistance", "battery.internal_resistance")
SUGGESTED_TARGETS: tuple[str, ...] = ("vehicle_speed", "battery_current", "battery_voltage")
_RESIDUAL_RATE = 10.0  # Hz at which simulation and measurement are compared
_FAILED_RESIDUAL = 10.0  # residual used where a replay ended early (in standard deviations)
_STEP = 0.02  # finite-difference step as a share of the parameter's allowed range
_TIME_STEP = "sim.time_step"
Array = NDArray[np.float64]
Progress = Callable[[int, float], object]  # (evaluations so far, current cost)


@dataclass
class CalibrationResult:
    """Outcome of a calibration."""

    start: dict[str, float]  # parameter → value before (friendly unit)
    fitted: dict[str, float]  # parameter → value after (friendly unit)
    before: list[FitQuality]  # fit quality with the starting values
    after: list[FitQuality]  # fit quality with the fitted values
    evaluations: int
    message: str
    at_limit: list[str] = field(default_factory=list)  # parameters that hit their range limit


def calibrate(params: ParamSet, recording: Recording, fit_params: list[str],
              targets: list[str], max_evaluations: int = 30, time_step: float = 0.002,
              progress: Progress | None = None) -> CalibrationResult:
    """Fit ``fit_params`` so the replay matches the ``targets`` channels of ``recording``.

    ``time_step`` (s) is the simulation step used during the fit; the default
    2 ms halves the computing time and changes the results very little. The
    before/after quality figures are computed with the same step.
    """
    params = params.copy()
    params.set(_TIME_STEP, max(time_step, params.num(_TIME_STEP)))
    if not fit_params or not targets:
        raise ValueError("Choose at least one parameter and one measured channel")
    lows, highs = [], []
    for name in fit_params:
        definition = params.registry.get(name)
        if definition.kind is not Kind.NUMBER or definition.min is None or definition.max is None:
            raise ValueError(f"'{name}' is not a number and cannot be calibrated")
        lows.append(definition.min)
        highs.append(definition.max)
    low, span = np.array(lows), np.array(highs) - np.array(lows)
    for name in targets:
        if name not in recording.data or recording.coverage(name) == 0.0:
            raise ValueError(f"the recording has no usable '{name}' channel")
    step = max(1, round(recording.rate / _RESIDUAL_RATE))
    scales = {name: float(np.nanstd(recording.data[name])) or 1.0 for name in targets}
    evaluations = 0

    def simulate(x: Array) -> tuple[Array, list[FitQuality]]:
        trial = params.copy()
        for name, value in zip(fit_params, low + x * span, strict=True):
            trial.set(name, float(value))
        result = replay(trial, recording, ideal_sensors=True)
        parts = []
        for name in targets:
            measured = result.data[f"{MEASURED_PREFIX}{name}"][::step]
            simulated = result.data[LOG_CHANNELS[name].sim_channel][::step]
            wanted = len(recording.data[name][::step])
            error = np.full(wanted, _FAILED_RESIDUAL)
            count = min(wanted, len(simulated))
            error[:count] = (simulated[:count] - measured[:count]) / scales[name]
            error[~np.isfinite(error)] = 0.0  # gaps in the measurement carry no information
            parts.append(error)
        return np.concatenate(parts), fit_quality(result)

    def residual(x: Array) -> Array:
        nonlocal evaluations
        values, _ = simulate(x)
        evaluations += 1
        if progress is not None:
            progress(evaluations, float(0.5 * np.sum(values**2)))
        return values

    start_values = np.array([params.num(name) for name in fit_params])
    x0 = np.clip((start_values - low) / span, 0.0, 1.0)
    _, before = simulate(x0)
    # The unknowns are scaled to 0…1 over each parameter's allowed range; SciPy then
    # uses ``diff_step`` directly as the step for the numerical derivative.
    # SciPy's ``max_nfev`` does not count the extra replays for the derivative
    # (one per parameter and iteration), so the budget is divided accordingly.
    iterations = max(2, max_evaluations // (len(fit_params) + 1))
    solution = least_squares(  # type: ignore[call-overload]
        residual, x0, bounds=(0.0, 1.0), diff_step=_STEP, max_nfev=iterations)
    _, after = simulate(solution.x)
    fitted_si = low + solution.x * span

    def shown(name: str, value: float) -> float:
        return float(f"{units.from_si(value, params.registry.get(name).unit):.6g}")

    return CalibrationResult(
        start={n: shown(n, v) for n, v in zip(fit_params, start_values, strict=True)},
        fitted={n: shown(n, v) for n, v in zip(fit_params, fitted_si, strict=True)},
        before=before, after=after, evaluations=evaluations, message=str(solution.message),
        at_limit=[n for n, x in zip(fit_params, solution.x, strict=True)
                  if x <= 1e-6 or x >= 1.0 - 1e-6])


def accept(profile: Profile, result: CalibrationResult, synthetic: bool) -> None:
    """Write the fitted values into a profile.

    The profile is marked as validated only when the recording was a real
    measurement — fitting to the synthetic example logs proves nothing about
    the real vehicle.
    """
    source = "the synthetic example log" if synthetic else "a ride log"
    for name, value in result.fitted.items():
        profile.params.set_display(name, value, Status.CALIBRATED)
        profile.notes[name] = f"fitted to {source} by the calibration tool"
    if not synthetic:
        profile.validated = True
