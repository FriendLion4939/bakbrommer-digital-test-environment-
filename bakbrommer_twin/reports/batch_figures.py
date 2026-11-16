"""Figures for sweeps, Monte Carlo runs and the optimiser."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from bakbrommer_twin.i18n import t
from bakbrommer_twin.reports import style


def _layout(figure: go.Figure, x_title: str, y_title: str, height: int = 380) -> go.Figure:
    figure.update_layout(height=height, paper_bgcolor=style.SURFACE, plot_bgcolor=style.SURFACE,
                         font={"color": style.TEXT, "size": 12},
                         margin={"l": 60, "r": 20, "t": 30, "b": 50},
                         legend={"orientation": "h", "y": 1.08, "x": 0})
    figure.update_xaxes(title_text=x_title, gridcolor=style.GRID, zeroline=False)
    figure.update_yaxes(title_text=y_title, gridcolor=style.GRID, zeroline=False)
    return figure


def _unsafe_marker(x: pd.Series[Any], y: pd.Series[Any], text: pd.Series[Any]) -> go.Scatter:
    return go.Scatter(
        x=x, y=y, mode="markers", name=t("batch.unsafe"), text=text,
        marker={"color": style.STATUS_CRITICAL, "size": 13, "symbol": "x",
                "line": {"color": style.SURFACE, "width": 1}},
        hovertemplate="%{text}<extra></extra>")


def sweep_line(table: pd.DataFrame, param: str, metric: str) -> go.Figure:
    """One swept parameter: the metric against the parameter; unsafe runs get a red cross."""
    ordered = table.sort_values(param)
    figure = go.Figure(go.Scatter(
        x=ordered[param], y=ordered[metric], mode="lines+markers", name=metric,
        line={"color": style.SERIES[0], "width": style.LINE_WIDTH}, marker={"size": 8},
        hovertemplate="%{x:g} → %{y:.4g}<extra></extra>"))
    unsafe = ordered[~ordered["safe"]]
    if len(unsafe):
        figure.add_trace(_unsafe_marker(unsafe[param], unsafe[metric], unsafe["violations"]))
    return _layout(figure, param, metric)


def sweep_heatmap(table: pd.DataFrame, param_x: str, param_y: str, metric: str) -> go.Figure:
    """Two swept parameters: the metric as a coloured grid; unsafe cells are crossed out."""
    grid = table.pivot(index=param_y, columns=param_x, values=metric)
    figure = go.Figure(go.Heatmap(
        x=[f"{v:g}" for v in grid.columns], y=[f"{v:g}" for v in grid.index], z=grid.values,
        colorscale=[[k / (len(style.SEQUENTIAL) - 1), c]
                    for k, c in enumerate(style.SEQUENTIAL)],
        colorbar={"title": metric}, xgap=2, ygap=2,
        text=np.vectorize(lambda v: f"{v:.3g}")(grid.values), texttemplate="%{text}",
        hovertemplate=f"{param_x} = %{{x}}<br>{param_y} = %{{y}}<br>%{{z:.4g}}<extra></extra>"))
    unsafe = table[~table["safe"]]
    if len(unsafe):
        figure.add_trace(_unsafe_marker(unsafe[param_x].map("{:g}".format),
                                        unsafe[param_y].map("{:g}".format),
                                        unsafe["violations"]))
    figure = _layout(figure, param_x, param_y, height=430)
    figure.update_xaxes(type="category")
    figure.update_yaxes(type="category")
    return figure


def histogram(table: pd.DataFrame, metric: str) -> go.Figure:
    """Monte Carlo: how the metric scatters; lines mark the 5 %, 50 % and 95 % points."""
    values = table[metric].dropna()
    figure = go.Figure(go.Histogram(
        x=values, nbinsx=min(30, max(5, len(values) // 3)), name=metric,
        marker={"color": style.SERIES[0], "line": {"color": style.SURFACE, "width": 2}},
        hovertemplate="%{x}: %{y}<extra></extra>"))
    if len(values):
        for share, label in ((5, "5 %"), (50, "50 %"), (95, "95 %")):
            figure.add_vline(x=float(np.percentile(values, share)), line_dash="dash",
                             line_color=style.TEXT_SECONDARY, annotation_text=label)
    return _layout(figure, metric, t("batch.samples"))


def optimiser_history(values: list[float | None], safe: list[bool],
                      minimise: bool, metric: str) -> go.Figure:
    """Optimiser: goal value of every candidate in run order, and the best safe value so far."""
    runs = np.arange(1, len(values) + 1)
    numbers = np.array([np.nan if v is None else v for v in values], dtype=float)
    ok = np.array(safe, dtype=bool)
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=runs[ok], y=numbers[ok], mode="markers",
                                name=t("batch.safe"),
                                marker={"color": style.SERIES[0], "size": 8}))
    figure.add_trace(go.Scatter(x=runs[~ok], y=numbers[~ok], mode="markers",
                                name=t("batch.unsafe"),
                                marker={"color": style.STATUS_CRITICAL, "size": 9,
                                        "symbol": "x"}))
    masked = np.where(ok, numbers, np.inf if minimise else -np.inf)
    best = np.minimum.accumulate(masked) if minimise else np.maximum.accumulate(masked)
    best = np.where(np.isfinite(best), best, np.nan)
    figure.add_trace(go.Scatter(x=runs, y=best, mode="lines", name=t("batch.best_so_far"),
                                line={"color": style.SERIES[2], "width": style.LINE_WIDTH}))
    return _layout(figure, t("batch.run_number"), metric)
