"""Top-down 2D animation of a run.

What is drawn, per frame:
* the route (grey band) and the path driven so far;
* the vehicle outline;
* each wheel as a rectangle whose fill shows its load (light blue = little,
  dark blue = much); a lifted wheel is drawn hollow in red and labelled
  "LIFT"; a wheel that spins, locks or slides gets an orange outline and the
  label "SLIP";
* one arrow per wheel for the tyre force on the vehicle (drive/brake and
  cornering combined), with the wheel torque in the hover text.
"""

from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go

from bakbrommer_twin.i18n import t
from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.physics.wheels import WHEEL_NAMES
from bakbrommer_twin.reports import style
from bakbrommer_twin.reports.figures import route_of
from bakbrommer_twin.sim.result import RunResult

_WHEEL_WIDTH = 0.12  # m, drawn tyre width
_FORCE_SCALE = 1.0 / 800.0  # m of arrow per newton
_ARROW_HEAD = 0.18  # m
_VIEW_HALF_WIDTH = 3.5  # m around the vehicle in "follow" view
_BOX_LENGTH = 0.9  # m of cargo box drawn ahead of the rear frame
Polygon = tuple[list[float], list[float]]


def _to_world(points: list[tuple[float, float]], x: float, y: float, yaw: float) -> Polygon:
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)
    return ([x + cos_y * px - sin_y * py for px, py in points],
            [y + sin_y * px + cos_y * py for px, py in points])


def _wheel_outline(cx: float, cy: float, steer: float, radius: float) -> list[tuple[float, float]]:
    """Corners of a wheel rectangle in body axes (closed polygon)."""
    cos_s, sin_s = math.cos(steer), math.sin(steer)
    half = _WHEEL_WIDTH / 2.0
    corners = [(radius, half), (radius, -half), (-radius, -half), (-radius, half), (radius, half)]
    return [(cx + cos_s * px - sin_s * py, cy + sin_s * px + cos_s * py) for px, py in corners]


def _arrow(cx: float, cy: float, fx: float, fy: float) -> list[tuple[float, float]]:
    """Line with a small head from (cx, cy) along the force (fx, fy), body axes."""
    dx, dy = fx * _FORCE_SCALE, fy * _FORCE_SCALE
    length = math.hypot(dx, dy)
    if length < 0.02:
        return [(cx, cy), (cx, cy)]
    ux, uy = dx / length, dy / length
    tip = (cx + dx, cy + dy)
    head = min(_ARROW_HEAD, 0.5 * length)
    left = (tip[0] - head * (ux + 0.5 * uy), tip[1] - head * (uy - 0.5 * ux))
    right = (tip[0] - head * (ux - 0.5 * uy), tip[1] - head * (uy + 0.5 * ux))
    return [(cx, cy), tip, left, tip, right]


class _Geometry:
    """Wheel positions for a handlebar angle, taken from the real steering model."""

    def __init__(self, params: ParamSet) -> None:
        self.vehicle = Vehicle(params)
        wheels = self.vehicle.wheels
        self.radii = [wheel.radius for wheel in wheels]
        front_x, rear_x = wheels[0].base_x, wheels[2].base_x
        half = 0.5 * (wheels[0].base_y - wheels[1].base_y)
        # cargo box over the front axle, tapering frame back to the rear wheel
        front, back, side = front_x + 0.5 * _BOX_LENGTH, front_x - 0.5 * _BOX_LENGTH, 0.8 * half
        self.body = [(front, side), (front, -side), (back, -side), (rear_x, -0.08),
                     (rear_x, 0.08), (back, side), (front, side)]

    def wheels_at(self, handlebar: float) -> list[tuple[float, float, float]]:
        """(x, y, steering angle) of each wheel in body axes."""
        self.vehicle.steering.apply(handlebar, self.vehicle.wheels)
        return [(wheel.x, wheel.y, wheel.steer) for wheel in self.vehicle.wheels]


def animation(result: RunResult, max_frames: int = 240, follow: bool = True) -> go.Figure:
    """Build the animated figure (play button and time slider included)."""
    params = ParamSet.from_display_dict(REGISTRY, result.meta.params)
    geometry = _Geometry(params)
    spin_limit = params.num("safety.slip_ratio_limit")
    slide_limit = params.num("safety.slip_angle_limit")
    lift_limit = params.num("safety.wheel_lift_min_height")
    time = result["time"]
    step = max(1, math.ceil(len(time) / max_frames))
    indices = list(range(0, len(time), step))
    top_load = max(float(np.max(result[f"load_{name}"])) for name in WHEEL_NAMES) or 1.0

    def frame_traces(i: int) -> list[go.Scatter]:
        x, y, yaw = float(result["x"][i]), float(result["y"][i]), float(result["yaw"][i])
        traces = [go.Scatter(x=result["x"][: i + 1 : step], y=result["y"][: i + 1 : step],
                             mode="lines", line={"color": style.SERIES[0], "width": 1.5},
                             hoverinfo="skip", showlegend=False)]
        bx, by = _to_world(geometry.body, x, y, yaw)
        traces.append(go.Scatter(x=bx, y=by, mode="lines", fill="toself",
                                 fillcolor="rgba(138,137,131,0.18)",
                                 line={"color": style.TEXT_SECONDARY, "width": 1.5},
                                 hoverinfo="skip", showlegend=False))
        labels_x, labels_y, labels = [], [], []
        for name, (wx, wy, steer), radius in zip(
                WHEEL_NAMES, geometry.wheels_at(float(result["steer"][i])), geometry.radii,
                strict=True):
            load = float(result[f"load_{name}"][i])
            gap = float(result[f"gap_{name}"][i])
            slip = abs(float(result[f"slip_ratio_{name}"][i]))
            slide = abs(float(result[f"slip_angle_{name}"][i]))
            lifted = gap > lift_limit
            slipping = not lifted and (slip > spin_limit or slide > slide_limit)
            outline = style.STATUS_CRITICAL if lifted else (
                style.STATUS_WARNING if slipping else style.TEXT)
            px, py = _to_world(_wheel_outline(wx, wy, steer, radius), x, y, yaw)
            traces.append(go.Scatter(
                x=px, y=py, mode="lines", fill="toself",
                fillcolor=style.SURFACE if lifted else style.sequential_colour(load / top_load),
                line={"color": outline, "width": 3 if lifted or slipping else 1},
                showlegend=False, hoveron="fills", name=t(f"subject.{name}"),
                text=(f"{t('subject.' + name)}<br>{t('anim.load')}: {load:.0f} N<br>"
                      f"{t('anim.lift')}: {gap * 1000:.0f} mm<br>"
                      f"{t('anim.slip')}: {slip * 100:.0f} %<br>"
                      f"{t('anim.torque')}: {float(result[f'torque_{name}'][i]):.0f} Nm"),
                hoverinfo="text"))
            heading_x = float(result[f"fx_{name}"][i])
            heading_y = float(result[f"fy_{name}"][i])
            force = (math.cos(steer) * heading_x - math.sin(steer) * heading_y,
                     math.sin(steer) * heading_x + math.cos(steer) * heading_y)
            ax, ay = _to_world(_arrow(wx, wy, *force), x, y, yaw)
            traces.append(go.Scatter(x=ax, y=ay, mode="lines", hoverinfo="skip", showlegend=False,
                                     line={"color": style.SERIES[1], "width": 2.5}))
            if lifted or slipping:
                lx, ly = _to_world([(wx, wy + (0.35 if wy >= 0 else -0.35))], x, y, yaw)
                labels_x += lx
                labels_y += ly
                labels.append(t("anim.lift_label") if lifted else t("anim.slip_label"))
        traces.append(go.Scatter(x=labels_x, y=labels_y, mode="text", text=labels,
                                 textfont={"color": style.TEXT, "size": 13}, hoverinfo="skip",
                                 showlegend=False))
        return traces

    def view(i: int) -> dict[str, object]:
        if not follow:
            return {}
        x, y = float(result["x"][i]), float(result["y"][i])
        return {"xaxis": {"range": [x - _VIEW_HALF_WIDTH, x + _VIEW_HALF_WIDTH]},
                "yaxis": {"range": [y - _VIEW_HALF_WIDTH, y + _VIEW_HALF_WIDTH]}}

    figure = go.Figure()
    route = route_of(result)
    figure.add_trace(go.Scatter(
        x=route.x if route else [], y=route.y if route else [], mode="lines",
        line={"color": style.NEUTRAL, "width": 14}, opacity=0.25, hoverinfo="skip",
        name=t("chart.route_planned")))
    # Colour key for the wheel load (an invisible point carrying the colour bar).
    figure.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers", showlegend=False, hoverinfo="skip",
        marker={"colorscale": [[k / (len(style.SEQUENTIAL) - 1), c]
                               for k, c in enumerate(style.SEQUENTIAL)],
                "cmin": 0, "cmax": top_load, "color": [0], "showscale": True,
                "colorbar": {"title": t("anim.load_key"), "thickness": 12, "len": 0.6}}))
    fixed = len(figure.data)
    figure.add_traces(frame_traces(0))
    moving = list(range(fixed, len(figure.data)))
    figure.frames = [
        go.Frame(data=frame_traces(i), traces=moving, name=f"{time[i]:.2f}", layout=view(i))
        for i in indices]
    frame_ms = max(40, round(1000 * step * (time[1] - time[0]))) if len(time) > 1 else 100
    play = {"frame": {"duration": frame_ms, "redraw": False}, "fromcurrent": True,
            "transition": {"duration": 0}}
    stop = {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}
    figure.update_layout(
        height=620, paper_bgcolor=style.SURFACE, plot_bgcolor=style.SURFACE,
        font={"color": style.TEXT}, margin={"l": 50, "r": 20, "t": 30, "b": 20},
        legend={"orientation": "h", "y": 1.05, "x": 0},
        updatemenus=[{"type": "buttons", "direction": "left", "x": 0.0, "y": -0.08,
                      "buttons": [{"label": t("anim.play"), "method": "animate",
                                   "args": [None, play]},
                                  {"label": t("anim.pause"), "method": "animate",
                                   "args": [[None], stop]}]}],
        sliders=[{"x": 0.18, "len": 0.82, "y": -0.04, "currentvalue": {"prefix": "t = ",
                                                                      "suffix": " s"},
                  "steps": [{"label": frame.name, "method": "animate", "args": [[frame.name], stop]}
                            for frame in figure.frames]}],
        **view(0))
    figure.update_xaxes(gridcolor=style.GRID, zeroline=False, title_text="x [m]")
    figure.update_yaxes(gridcolor=style.GRID, zeroline=False, title_text="y [m]",
                        scaleanchor="x", scaleratio=1)
    return figure
