"""Curves and maps that follow from the parameters (Parameters page, "Curves" tab).

To add a curve: write a function ``(params) -> go.Figure`` and add it to
``CURVES`` with a translation key ``curves.<key>``.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from bakbrommer_twin.i18n import t
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics import performance
from bakbrommer_twin.physics.battery import Battery
from bakbrommer_twin.physics.engine import Engine
from bakbrommer_twin.physics.motors import ElectricDrive
from bakbrommer_twin.physics.surfaces import load_surfaces
from bakbrommer_twin.physics.tyres import force_curve
from bakbrommer_twin.reports import style

_POINTS = 60
_SEQUENTIAL_SCALE = [[k / (len(style.SEQUENTIAL) - 1), c] for k, c in enumerate(style.SEQUENTIAL)]


def _finish(figure: go.Figure, height: int = 420) -> go.Figure:
    figure.update_layout(height=height, paper_bgcolor=style.SURFACE, plot_bgcolor=style.SURFACE,
                         font={"color": style.TEXT, "size": 12},
                         margin={"l": 60, "r": 20, "t": 50, "b": 50},
                         legend={"orientation": "h", "y": -0.18, "x": 0})
    figure.update_xaxes(gridcolor=style.GRID, zeroline=False)
    figure.update_yaxes(gridcolor=style.GRID, zeroline=False)
    return figure


def tyre_curves(params: ParamSet) -> go.Figure:
    """Friction used (force ÷ wheel load) against slip, for every surface (front tyre)."""
    figure = make_subplots(rows=1, cols=2, subplot_titles=[t("curves.tyre_long"),
                                                           t("curves.tyre_lat")])
    slip_peak = params.num("tyre.front.slip_ratio_at_peak")
    angle_peak = params.num("tyre.front.slip_angle_at_peak")
    lateral = params.num("tyre.front.lateral_friction_ratio")
    slip = np.linspace(0.0, 0.6, _POINTS)
    angle = np.linspace(0.0, math.radians(25.0), _POINTS)
    for colour, surface in zip(style.SERIES, load_surfaces(params).values(), strict=False):
        scale = surface.peak_slip_scale
        along = [surface.friction * force_curve(surface, s / (slip_peak * scale)) for s in slip]
        across = [surface.friction * lateral * force_curve(
            surface, math.tan(a) / (math.tan(angle_peak) * scale)) for a in angle]
        name = surface.name.replace("_", " ")
        line = {"color": colour, "width": style.LINE_WIDTH}
        figure.add_trace(go.Scatter(x=slip * 100, y=along, name=name, line=line,
                                    legendgroup=name), row=1, col=1)
        figure.add_trace(go.Scatter(x=np.degrees(angle), y=across, name=name, line=line,
                                    legendgroup=name, showlegend=False), row=1, col=2)
    figure.update_xaxes(title_text=t("curves.slip_ratio"), row=1, col=1)
    figure.update_xaxes(title_text=t("curves.slip_angle"), row=1, col=2)
    figure.update_yaxes(title_text=t("curves.friction_used"), row=1, col=1)
    return _finish(figure)


def motor_map(params: ParamSet) -> go.Figure:
    """Efficiency of one motor (battery → wheel) over speed and torque, with its torque limit."""
    drive = ElectricDrive(params)
    voltage = performance.nominal_battery_voltage(params)
    radius = drive.wheel_radius
    top = drive.modulation * voltage * drive.field_weakening / drive.ke  # no-load speed, rad/s
    speeds = np.linspace(0.02 * top, top, _POINTS)
    torques = np.linspace(1.0, drive.kt * drive.peak_current, _POINTS)
    limit = np.array([drive.max_drive_torque(w, voltage) for w in speeds])
    grid = np.array([[drive.efficiency(tq, w) * 100 if tq <= limit[i] else np.nan
                      for i, w in enumerate(speeds)] for tq in torques])
    kmh = speeds * radius * 3.6
    figure = go.Figure(go.Heatmap(
        x=kmh, y=torques, z=grid, colorscale=_SEQUENTIAL_SCALE, zmin=40, zmax=95,
        colorbar={"title": "%"},
        hovertemplate="%{x:.0f} km/h, %{y:.0f} Nm: %{z:.0f} %<extra></extra>"))
    figure.add_trace(go.Scatter(x=kmh, y=limit, mode="lines", name=t("curves.torque_limit"),
                                line={"color": style.SERIES[1], "width": style.LINE_WIDTH}))
    figure.update_xaxes(title_text="km/h")
    figure.update_yaxes(title_text="Nm")
    figure.update_layout(title=t("curves.motor_title", voltage=voltage,
                                 current=drive.line_limit))
    return _finish(figure)


def engine_curves(params: ParamSet) -> go.Figure:
    """Petrol engine: torque and power at full throttle, and the fuel map."""
    engine = Engine(params)
    low, high = engine.torque_curve.x_min, engine.rev_limit
    speeds = np.linspace(low, high, _POINTS)
    torque = np.array([engine.torque_curve(w) for w in speeds])
    rpm = speeds * 60.0 / (2.0 * math.pi)
    figure = make_subplots(rows=1, cols=3, subplot_titles=[
        t("curves.engine_torque"), t("curves.engine_power"), t("curves.fuel_map")])
    figure.add_trace(go.Scatter(x=rpm, y=torque, showlegend=False,
                                line={"color": style.SERIES[0], "width": style.LINE_WIDTH}),
                     row=1, col=1)
    figure.add_trace(go.Scatter(x=rpm, y=torque * speeds / 1000.0, showlegend=False,
                                line={"color": style.SERIES[1], "width": style.LINE_WIDTH}),
                     row=1, col=2)
    # Specific fuel consumption (g/kWh) = fuel mass flow ÷ shaft power, from the same
    # formula the simulator uses: fuel power = load·(T_wot + T_f)·ω / η.
    loads = np.linspace(0.15, 1.0, 30)
    bsfc = np.full((len(loads), len(speeds)), np.nan)
    shaft = np.zeros_like(bsfc)
    for j, w in enumerate(speeds):
        friction = engine.friction(w)
        indicated_max = engine.torque_curve(w) + friction
        for i, load in enumerate(loads):
            net = load * indicated_max - friction
            shaft[i, j] = net
            if net > 0.2:
                fuel = load * indicated_max * w / (engine.efficiency * engine.heating_value)
                bsfc[i, j] = fuel / (net * w) * 3.6e9  # kg/J → g/kWh
    figure.add_trace(go.Heatmap(
        x=rpm, y=loads * 100, z=bsfc, colorscale=_SEQUENTIAL_SCALE, zmin=250, zmax=700,
        colorbar={"title": "g/kWh"}, customdata=shaft,
        hovertemplate="%{x:.0f} rpm, %{y:.0f} % load (%{customdata:.1f} Nm): "
                      "%{z:.0f} g/kWh<extra></extra>"), row=1, col=3)
    for column in (1, 2, 3):
        figure.update_xaxes(title_text="rpm", row=1, col=column)
    figure.update_yaxes(title_text="Nm", row=1, col=1)
    figure.update_yaxes(title_text="kW", row=1, col=2)
    figure.update_yaxes(title_text=t("curves.engine_load"), row=1, col=3)
    return _finish(figure)


def battery_curve(params: ParamSet) -> go.Figure:
    """Pack voltage against state of charge: at rest and at the BMS current limit."""
    battery = Battery(params)
    limit = battery.discharge_limit
    charge = np.linspace(0.0, 1.0, _POINTS)
    rest = []
    for soc in charge:
        battery.soc = float(soc)
        rest.append(battery.open_circuit_voltage())
    loaded = np.array(rest) - limit * battery.r0
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=charge * 100, y=rest, name=t("curves.battery_rest"),
                                line={"color": style.SERIES[0], "width": style.LINE_WIDTH}))
    figure.add_trace(go.Scatter(x=charge * 100, y=loaded,
                                name=t("curves.battery_loaded", current=limit),
                                line={"color": style.SERIES[1], "width": style.LINE_WIDTH}))
    figure.add_hline(y=params.num("battery.min_voltage"), line_dash="dash",
                     line_color=style.STATUS_CRITICAL,
                     annotation_text=t("curves.battery_minimum"))
    figure.update_xaxes(title_text=t("curves.state_of_charge"))
    figure.update_yaxes(title_text="V")
    return _finish(figure)


# key (translation ``curves.<key>``) → figure builder
CURVES: dict[str, Callable[[ParamSet], go.Figure]] = {
    "tyres": tyre_curves,
    "motor": motor_map,
    "engine": engine_curves,
    "battery": battery_curve,
}
