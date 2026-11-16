"""Conversion between a :class:`Scenario` and the editable tables of the scenario page."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.types import Kind, ParamValue
from bakbrommer_twin.scenarios.scenario import Scenario

SEGMENT_COLUMNS: tuple[str, ...] = (
    "type", "length_m", "radius_m", "angle_deg", "cone_spacing_m", "cones", "lateral_offset_m",
    "points", "speed_kmh", "speed_end_kmh", "surface", "surface_left", "surface_right",
    "gradient_pct", "throttle", "brake", "stop_s")
EVENT_COLUMNS: tuple[str, ...] = ("at_time_s", "at_distance_m", "set_mode")
METRIC_COLUMNS: tuple[str, ...] = ("type", "speed_kmh", "from_kmh")
OVERRIDE_COLUMNS: tuple[str, ...] = ("parameter", "value")
_TEXT_COLUMNS = ("type", "points", "surface", "surface_left", "surface_right", "set_mode",
                 "parameter", "value")


def _points_text(points: list[tuple[float, float]] | None) -> str | None:
    return None if not points else "; ".join(f"{x:g}, {y:g}" for x, y in points)


def _parse_points(text: str) -> list[tuple[float, float]]:
    points = []
    for pair in text.split(";"):
        if pair.strip():
            x, y = pair.split(",")
            points.append((float(x), float(y)))
    return points


def _frame(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=list(columns))
    for column in columns:
        frame[column] = frame[column].astype("string" if column in _TEXT_COLUMNS else "Float64")
    return frame


def scenario_frames(scenario: Scenario) -> dict[str, pd.DataFrame]:
    """The four editable tables of a scenario."""
    segments = []
    for segment in scenario.route:
        row = segment.model_dump()
        row["points"] = _points_text(segment.points)
        segments.append(row)
    overrides = [{"parameter": name, "value": str(value)}
                 for name, value in scenario.param_overrides.items()]
    return {
        "segments": _frame(segments, SEGMENT_COLUMNS),
        "events": _frame([e.model_dump() for e in scenario.events], EVENT_COLUMNS),
        "metrics": _frame([m.model_dump() for m in scenario.metrics], METRIC_COLUMNS),
        "overrides": _frame(overrides, OVERRIDE_COLUMNS),
    }


def _rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Table rows as dictionaries without empty cells."""
    rows = []
    for record in frame.to_dict("records"):
        row = {}
        for key, value in record.items():
            if value is None or value is pd.NA:
                continue
            if isinstance(value, float) and math.isnan(value):
                continue
            if isinstance(value, str) and not value.strip():
                continue
            row[str(key)] = value
        if row:
            rows.append(row)
    return rows


def _override_value(name: str, text: str) -> ParamValue:
    kind = REGISTRY.get(name).kind
    if kind is Kind.FLAG:
        return text.strip().lower() in ("true", "yes", "1", "on")
    if kind is Kind.CHOICE:
        return text.strip()
    if kind is Kind.CURVE:
        return [float(item) for item in text.strip("[] ").split(",") if item.strip()]
    return int(float(text)) if kind is Kind.INTEGER else float(text)


def build_scenario(fields: dict[str, Any], frames: dict[str, pd.DataFrame]) -> Scenario:
    """Combine the simple fields and the edited tables into a validated scenario.

    Raises ``ValueError`` with a readable message when something is wrong.
    """
    segments = _rows(frames["segments"])
    for row in segments:
        if "points" in row:
            row["points"] = _parse_points(row["points"])
        if "cones" in row:
            row["cones"] = int(row["cones"])
    overrides = {row["parameter"]: _override_value(row["parameter"], str(row.get("value", "")))
                 for row in _rows(frames["overrides"]) if "parameter" in row}
    return Scenario.model_validate({
        **fields, "route": segments, "events": _rows(frames["events"]),
        "metrics": _rows(frames["metrics"]), "param_overrides": overrides})
