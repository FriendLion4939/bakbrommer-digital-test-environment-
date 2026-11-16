"""Figures for the scenario editor: route preview, speed plan, drawing canvas."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import groupby

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from bakbrommer_twin.i18n import t
from bakbrommer_twin.params.definitions.wheels import SURFACE_NAMES
from bakbrommer_twin.reports import style
from bakbrommer_twin.scenarios.route import Route


def route_preview(route: Route, plan: Sequence[float]) -> go.Figure:
    """Left: the route from above, coloured by surface. Right: planned speed and gradient."""
    figure = make_subplots(
        rows=2, cols=2, column_widths=[0.55, 0.45], specs=[[{"rowspan": 2}, {}], [None, {}]],
        subplot_titles=[t("scenarios.preview_route"), t("scenarios.preview_speed"),
                        t("scenarios.preview_gradient")], vertical_spacing=0.16)
    start = 0
    seen: set[str] = set()
    for surface, group in groupby(route.surface_center):
        count = len(list(group))
        stop = min(len(route) - 1, start + count)
        figure.add_trace(go.Scatter(
            x=route.x[start:stop + 1], y=route.y[start:stop + 1], mode="lines",
            name=surface.replace("_", " "), legendgroup=surface, showlegend=surface not in seen,
            line={"color": style.SERIES[SURFACE_NAMES.index(surface) % len(style.SERIES)],
                  "width": 4}, hoverinfo="name"), row=1, col=1)
        seen.add(surface)
        start += count
    figure.add_trace(go.Scatter(
        x=[route.x[0]], y=[route.y[0]], mode="markers+text", text=[t("scenarios.start")],
        textposition="top center", showlegend=False, hoverinfo="skip",
        marker={"color": style.TEXT, "size": 11, "symbol": "circle"}), row=1, col=1)
    if route.stops:
        figure.add_trace(go.Scatter(
            x=[route.x[i] for i, _ in route.stops], y=[route.y[i] for i, _ in route.stops],
            mode="markers", name=t("scenarios.stop"), hovertemplate="%{text}<extra></extra>",
            text=[f"{t('scenarios.stop')} {seconds:g} s" for _, seconds in route.stops],
            marker={"color": style.STATUS_CRITICAL, "size": 10, "symbol": "square"}),
            row=1, col=1)
    distance = np.array(route.s)
    planned = np.array([np.nan if np.isinf(v) else v * 3.6 for v in plan])
    figure.add_trace(go.Scatter(
        x=distance, y=np.array(route.speed) * 3.6, mode="lines", name=t("scenarios.speed_limit"),
        line={"color": style.NEUTRAL, "width": 1.5, "dash": "dot"}), row=1, col=2)
    figure.add_trace(go.Scatter(
        x=distance, y=planned, mode="lines", name=t("scenarios.speed_plan"),
        line={"color": style.SERIES[0], "width": style.LINE_WIDTH}), row=1, col=2)
    figure.add_trace(go.Scatter(
        x=distance, y=np.array(route.grade) * 100.0, mode="lines", showlegend=False,
        name=t("scenarios.preview_gradient"),
        line={"color": style.SERIES[1], "width": style.LINE_WIDTH}), row=2, col=2)
    figure.update_layout(height=470, paper_bgcolor=style.SURFACE, plot_bgcolor=style.SURFACE,
                         font={"color": style.TEXT, "size": 12},
                         margin={"l": 50, "r": 20, "t": 40, "b": 40},
                         legend={"orientation": "h", "y": -0.12, "x": 0})
    figure.update_xaxes(gridcolor=style.GRID, zeroline=False)
    figure.update_yaxes(gridcolor=style.GRID, zeroline=False)
    figure.update_yaxes(scaleanchor="x", scaleratio=1, row=1, col=1)
    figure.update_xaxes(title_text="m", row=2, col=2)
    figure.update_yaxes(title_text="km/h", row=1, col=2)
    figure.update_yaxes(title_text="%", row=2, col=2)
    return figure


def drawing_canvas(points: Sequence[tuple[float, float]], length: float, half_width: float,
                   spacing: float) -> go.Figure:
    """A grid of clickable dots plus the route drawn so far (start at 0,0 heading right)."""
    xs = np.arange(0.0, length + spacing / 2, spacing)
    ys = np.arange(-half_width, half_width + spacing / 2, spacing)
    grid_x, grid_y = np.meshgrid(xs, ys)
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=grid_x.ravel(), y=grid_y.ravel(), mode="markers", name="grid", showlegend=False,
        marker={"color": style.GRID, "size": 9},
        hovertemplate="%{x:g} m, %{y:g} m<extra></extra>"))
    drawn = [(0.0, 0.0), *points]
    figure.add_trace(go.Scatter(
        x=[p[0] for p in drawn], y=[p[1] for p in drawn], mode="lines+markers+text",
        showlegend=False, hoverinfo="skip", text=[t("scenarios.start"), *[
            str(i) for i in range(1, len(drawn))]], textposition="top center",
        line={"color": style.SERIES[0], "width": style.LINE_WIDTH},
        marker={"color": style.SERIES[0], "size": 10}))
    figure.update_layout(height=430, paper_bgcolor=style.SURFACE, plot_bgcolor=style.SURFACE,
                         margin={"l": 40, "r": 10, "t": 10, "b": 40}, dragmode=False,
                         clickmode="event+select")
    figure.update_xaxes(title_text=t("scenarios.draw_forward"), showgrid=False, zeroline=False)
    figure.update_yaxes(title_text=t("scenarios.draw_left"), showgrid=False, zeroline=False,
                        scaleanchor="x", scaleratio=1)
    return figure
