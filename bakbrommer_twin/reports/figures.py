"""Plotly figures: synchronised time-series charts and the route map."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import plotly.graph_objects as go
from numpy.typing import NDArray
from plotly.subplots import make_subplots

from bakbrommer_twin.i18n import t
from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.reports import style
from bakbrommer_twin.reports.chart_defs import ChartDef
from bakbrommer_twin.scenarios.route import Route
from bakbrommer_twin.scenarios.scenario import REPLAY_CATEGORY, Scenario
from bakbrommer_twin.sim.result import RunResult

_ROW_HEIGHT = 230  # px per stacked chart
Array = NDArray[np.float64]


def thin(values: Array, limit: int = style.MAX_POINTS) -> Array:
    """Every n-th sample so that at most ``limit`` remain (keeps the last one)."""
    if len(values) <= limit:
        return values
    step = int(np.ceil(len(values) / limit))
    picked = values[::step]
    # Decided by position, not by value, so every channel of a run thins to the same length.
    return picked if (len(values) - 1) % step == 0 else np.append(picked, values[-1])


def chart_title(chart: ChartDef, result: RunResult) -> str:
    """Translated title with unit, e.g. ``Wheel loads [N]``."""
    if chart.key.startswith("custom_"):
        # "Sensor: Vehicle speed" and "Measured: Vehicle speed" share one title
        names = dict.fromkeys(result.info(name).label.split(": ", 1)[-1]
                              for name in chart.channels)
        title = ", ".join(names)
    else:
        title = t(f"chart.{chart.key}")
    unit = result.info(chart.channels[0]).unit
    return title if unit in ("", "-") else f"{title} [{unit}]"


def _base_layout(figure: go.Figure, height: int) -> None:
    figure.update_layout(
        height=height, paper_bgcolor=style.SURFACE, plot_bgcolor=style.SURFACE,
        font={"color": style.TEXT, "size": 12}, hovermode="x unified",
        margin={"l": 60, "r": 20, "t": 40, "b": 45},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0})
    figure.update_xaxes(gridcolor=style.GRID, zeroline=False, linecolor=style.GRID)
    figure.update_yaxes(gridcolor=style.GRID, zerolinecolor=style.NEUTRAL, zerolinewidth=1)


def time_series(results: Sequence[RunResult], charts: Sequence[ChartDef],
                x_channel: str = "time") -> go.Figure:
    """Stacked charts with a shared x-axis: zooming one zooms all.

    With several runs, a signal keeps its colour in every run and the runs
    differ by line style (solid, dashed, dotted).
    """
    first = results[0]
    figure = make_subplots(
        rows=len(charts), cols=1, shared_xaxes=True, vertical_spacing=min(0.12, 0.42 / len(charts)),
        subplot_titles=[chart_title(chart, first) for chart in charts])
    several = len(results) > 1
    for row, chart in enumerate(charts, start=1):
        for colour, name in zip(style.SERIES, chart.channels, strict=False):
            for run_index, result in enumerate(results):
                if name not in result.data:
                    continue
                label = result.info(name).label
                hover = f"{label} — {result.meta.name}" if several else label
                # Each chart's legend names its signals once (colour); with several
                # runs a separate key at the top explains the line styles.
                figure.add_trace(go.Scatter(
                    x=thin(result.display(x_channel)), y=thin(result.display(name)),
                    name=label, mode="lines", legend=f"legend{row + 1}",
                    showlegend=run_index == 0,
                    line={"color": colour, "width": style.LINE_WIDTH,
                          "dash": style.RUN_DASHES[run_index % len(style.RUN_DASHES)]},
                    hovertemplate="%{y:.4g}<extra>" + hover + "</extra>"), row=row, col=1)
    if several:
        for run_index, result in enumerate(results):
            figure.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines", name=result.meta.name, legend="legend",
                line={"color": style.TEXT_SECONDARY, "width": style.LINE_WIDTH,
                      "dash": style.RUN_DASHES[run_index % len(style.RUN_DASHES)]}))
    _base_layout(figure, _ROW_HEIGHT * len(charts) + (100 if several else 60))
    figure.update_layout(margin={"t": 80 if several else 40},
                         legend={"y": 0.995, "yanchor": "top", "yref": "container",
                                 "x": 0.0, "orientation": "h"})
    # Titles sit at the top-left of each chart, its legend at the top-right above the
    # plot area, so neither covers data.
    for annotation in figure.layout.annotations:
        annotation.update(x=0.0, xanchor="left", font={"size": 14})
    for row in range(1, len(charts) + 1):
        axis = figure.layout[f"yaxis{row if row > 1 else ''}"]
        figure.layout[f"legend{row + 1}"] = {
            "x": 1.0, "xanchor": "right", "y": axis.domain[1], "yanchor": "bottom",
            "orientation": "h", "bgcolor": "rgba(0,0,0,0)", "font": {"size": 11}}
    info = first.info(x_channel)
    figure.update_xaxes(title_text=f"{info.label} [{info.unit}]", row=len(charts), col=1)
    return figure


def route_of(result: RunResult) -> Route | None:
    """Rebuild the route a run was driven on (None for replays without a route)."""
    params = ParamSet.from_display_dict(REGISTRY, result.meta.params)
    scenario = Scenario.model_validate(result.meta.scenario)
    if scenario.category == REPLAY_CATEGORY:
        return None
    return Route(scenario.route, params.num("sim.route_sample_spacing"),
                 params.choice("environment.default_surface"))


def _event_text(kind: str, subject: str, start: float) -> str:
    where = t("subject." + subject) if subject else ""
    return f"{t('event.' + kind)} {where} @ {start:.1f} s"


def route_map(results: Sequence[RunResult]) -> go.Figure:
    """Top view: the planned route and the path each run actually drove."""
    figure = go.Figure()
    route = route_of(results[0])
    if route is not None:
        figure.add_trace(go.Scatter(
            x=route.x, y=route.y, mode="lines", name=t("chart.route_planned"),
            line={"color": style.NEUTRAL, "width": 6}, opacity=0.35, hoverinfo="skip"))
    for colour, result in zip(style.SERIES, results, strict=False):
        figure.add_trace(go.Scatter(
            x=thin(result["x"]), y=thin(result["y"]), mode="lines", name=result.meta.name,
            line={"color": colour, "width": style.LINE_WIDTH},
            customdata=np.stack([thin(result["time"]), thin(result.display("speed"))], axis=-1),
            hovertemplate="t = %{customdata[0]:.1f} s<br>%{customdata[1]:.1f} km/h<extra></extra>"))
        lifts = [e for e in result.meta.events if e.kind in ("wheel_lift", "rollover")]
        if lifts:
            times = np.array([e.start for e in lifts])
            figure.add_trace(go.Scatter(
                x=np.interp(times, result["time"], result["x"]),
                y=np.interp(times, result["time"], result["y"]), mode="markers",
                name=f"{t('chart.lift_marker')} — {result.meta.name}",
                marker={"color": style.STATUS_CRITICAL, "size": 9, "symbol": "x",
                        "line": {"color": style.SURFACE, "width": 1}},
                text=[_event_text(e.kind, e.subject, e.start) for e in lifts],
                hovertemplate="%{text}<extra></extra>"))
    _base_layout(figure, 480)
    figure.update_layout(hovermode="closest")
    figure.update_xaxes(title_text="x [m]")
    figure.update_yaxes(title_text="y [m]", scaleanchor="x", scaleratio=1)
    return figure
