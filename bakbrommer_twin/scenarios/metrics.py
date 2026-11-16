"""Scenario-specific results (e.g. "time from 0 to 50 km/h").

A scenario lists the metrics it wants under ``metrics:``. Each ``type`` maps
to one function here. To add a metric type: write a function taking
``(data, events, spec)`` and returning a :class:`Metric`, and add it to
``_METRICS``.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from bakbrommer_twin.scenarios.scenario import MetricSpec
from bakbrommer_twin.sim.result import Metric
from bakbrommer_twin.sim.safety import SafetyEvent

Data = dict[str, NDArray[np.float64]]
_FRONT_WHEELS = ("fl", "fr")
_BRAKE_ONSET = 0.05  # lever position that counts as "braking has started"
_STEADY_WINDOW = 2.0  # s at the end of the run averaged for "steady" values


def _first_crossing(time: NDArray[np.float64], signal: NDArray[np.float64],
                    level: float) -> float | None:
    """Time at which ``signal`` first rises through ``level`` (linear interpolation)."""
    above = np.nonzero(signal >= level)[0]
    if len(above) == 0:
        return None
    i = int(above[0])
    if i == 0:
        return float(time[0])
    fraction = (level - signal[i - 1]) / (signal[i] - signal[i - 1])
    return float(time[i - 1] + fraction * (time[i] - time[i - 1]))


def _time_to_speed(data: Data, events: list[SafetyEvent], spec: MetricSpec) -> Metric:
    target = (spec.speed_kmh or 0.0) / 3.6
    start_speed = (spec.from_kmh or 0.0) / 3.6
    end = _first_crossing(data["time"], data["speed"], target)
    start = _first_crossing(data["time"], data["speed"], start_speed) if start_speed > 0 else 0.0
    value = None if end is None or start is None else end - start
    label = f"Time {spec.from_kmh or 0:g}–{spec.speed_kmh:g} km/h"
    return Metric(key=f"time_{spec.from_kmh or 0:g}_{spec.speed_kmh:g}", label=label,
                  value=value, unit="s")


def _top_speed(data: Data, events: list[SafetyEvent], spec: MetricSpec) -> Metric:
    return Metric(key="top_speed", label="Top speed", value=float(np.max(data["speed"])),
                  unit="km/h")


def _steady_speed(data: Data, events: list[SafetyEvent], spec: MetricSpec) -> Metric:
    window = data["time"] >= data["time"][-1] - _STEADY_WINDOW
    return Metric(key="steady_speed", label="Speed held at the end",
                  value=float(np.mean(data["speed"][window])), unit="km/h")


def _braking(data: Data) -> tuple[int, int] | None:
    """Sample indices of brake onset and of standstill (or the end of the run)."""
    braking = np.nonzero(np.maximum(data["brake_front"], data["brake_rear"]) > _BRAKE_ONSET)[0]
    if len(braking) == 0:
        return None
    return int(braking[0]), len(data["time"]) - 1


def _braking_distance(data: Data, events: list[SafetyEvent], spec: MetricSpec) -> Metric:
    span = _braking(data)
    value = None
    if span is not None:
        start, end = span
        value = float(np.trapezoid(data["speed"][start:end + 1], data["time"][start:end + 1]))
    return Metric(key="braking_distance", label="Braking distance", value=value, unit="m")


def _braking_deceleration(data: Data, events: list[SafetyEvent], spec: MetricSpec) -> Metric:
    span = _braking(data)
    value = None
    if span is not None and span[1] > span[0]:
        start, end = span
        elapsed = float(data["time"][end] - data["time"][start])
        value = float(data["speed"][start] - data["speed"][end]) / elapsed
    return Metric(key="braking_deceleration", label="Average braking deceleration", value=value,
                  unit="m/s²")


def _first_front_lift(events: list[SafetyEvent]) -> float | None:
    starts = [e.start for e in events if e.kind == "wheel_lift" and e.subject in _FRONT_WHEELS]
    return min(starts) if starts else None


def _wheel_lift_speed(data: Data, events: list[SafetyEvent], spec: MetricSpec) -> Metric:
    start = _first_front_lift(events)
    value = None if start is None else float(np.interp(start, data["time"], data["speed"]))
    return Metric(key="wheel_lift_speed", label="Speed at first front wheel lift", value=value,
                  unit="km/h")


def _wheel_lift_accel(data: Data, events: list[SafetyEvent], spec: MetricSpec) -> Metric:
    start = _first_front_lift(events)
    value = None
    if start is not None:
        value = float(np.interp(start, data["time"], np.abs(data["accel_y"])))
    return Metric(key="wheel_lift_lateral_accel", label="Cornering force at first wheel lift",
                  value=value, unit="g")


def _finish_time(data: Data, events: list[SafetyEvent], spec: MetricSpec) -> Metric:
    return Metric(key="finish_time", label="Time to finish", value=float(data["time"][-1]),
                  unit="s")


def _max_route_offset(data: Data, events: list[SafetyEvent], spec: MetricSpec) -> Metric:
    return Metric(key="max_route_offset", label="Largest distance from the route",
                  value=float(np.max(np.abs(data["route_offset"]))), unit="m")


_METRICS: dict[str, Callable[[Data, list[SafetyEvent], MetricSpec], Metric]] = {
    "time_to_speed": _time_to_speed,
    "top_speed": _top_speed,
    "steady_speed": _steady_speed,
    "braking_distance": _braking_distance,
    "braking_deceleration": _braking_deceleration,
    "wheel_lift_speed": _wheel_lift_speed,
    "wheel_lift_lateral_accel": _wheel_lift_accel,
    "finish_time": _finish_time,
    "max_route_offset": _max_route_offset,
}
METRIC_TYPES: tuple[str, ...] = tuple(_METRICS)


def evaluate(specs: list[MetricSpec], data: Data, events: list[SafetyEvent]) -> list[Metric]:
    """Calculate all metrics a scenario asks for."""
    results = []
    for spec in specs:
        if spec.type not in _METRICS:
            raise ValueError(f"unknown metric type '{spec.type}'; choose from {METRIC_TYPES}")
        results.append(_METRICS[spec.type](data, events, spec))
    return results


def expected_keys(specs: list[MetricSpec]) -> list[tuple[str, str]]:
    """(key, label) of the metrics a list of specs will produce, without running anything."""
    blank = {name: np.zeros(2) for name in ("time", "speed", "brake_front", "brake_rear",
                                            "accel_y", "route_offset")}
    return [(metric.key, metric.label) for metric in evaluate(specs, blank, [])]
