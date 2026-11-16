"""Recorded channels: every signal stored in a run result.

A channel is a name, a friendly unit for display, a label and a getter that
reads the value (in SI) from the running simulation. Values are stored in SI;
convert with ``params.units.from_si(value, channel.unit)`` for display.

To add a channel: append one ``ChannelDef`` in the matching ``_*_channels``
function. It is then recorded, exported to CSV and selectable in the charts.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bakbrommer_twin.params.definitions.sensors import SENSOR_SPECS
from bakbrommer_twin.params.definitions.wheels import SURFACE_NAMES
from bakbrommer_twin.physics.motors import ElectricDrive
from bakbrommer_twin.physics.wheels import WHEEL_NAMES, Wheel
from bakbrommer_twin.sensors.model import Sensor
from bakbrommer_twin.sim.safety import rollover_margin

if TYPE_CHECKING:
    from bakbrommer_twin.sim.simulator import Simulation

WHEEL_TITLES = ("front-left", "front-right", "rear")


@dataclass(frozen=True)
class ChannelDef:
    """One recorded signal."""

    name: str
    unit: str  # friendly unit for display; stored values are SI
    label: str
    group: str


Getter = Callable[[], float]


def _motion(sim: Simulation) -> list[tuple[ChannelDef, Getter]]:
    c = sim.vehicle.chassis
    g = "Motion"
    return [
        (ChannelDef("time", "s", "Time", g), lambda: sim.time),
        (ChannelDef("distance", "m", "Distance along route", g), lambda: sim.distance),
        (ChannelDef("x", "m", "Position X", g), lambda: c.x),
        (ChannelDef("y", "m", "Position Y", g), lambda: c.y),
        (ChannelDef("yaw", "deg", "Heading", g), lambda: c.yaw),
        (ChannelDef("speed", "km/h", "Speed", g), lambda: c.u),
        (ChannelDef("target_speed", "km/h", "Target speed", g),
         lambda: sim.driver.target_speed),
        (ChannelDef("lateral_speed", "m/s", "Sideways speed", g), lambda: c.v),
        (ChannelDef("yaw_rate", "deg/s", "Yaw rate", g), c.yaw_rate),
        (ChannelDef("roll", "deg", "Roll angle", g), lambda: c.roll),
        (ChannelDef("pitch", "deg", "Pitch angle", g), lambda: c.pitch),
        (ChannelDef("roll_rate", "deg/s", "Roll rate", g), lambda: c.p),
        (ChannelDef("accel_x", "m/s²", "Felt acceleration, forward", g), lambda: c.accel_x),
        (ChannelDef("accel_y", "m/s²", "Felt acceleration, left", g), lambda: c.accel_y),
        (ChannelDef("accel_z", "m/s²", "Felt acceleration, up", g), lambda: c.accel_z),
        (ChannelDef("route_offset", "m", "Distance left of route", g),
         lambda: sim.route_offset),
        (ChannelDef("grade", "%", "Road gradient", g),
         lambda: sim.env.grade_sin / sim.env.grade_cos),
        (ChannelDef("rollover_margin", "-", "Rollover margin (1 = safe, 0 = wheel lifts)", g),
         lambda: rollover_margin(sim.vehicle.wheels)),
    ]


def _rider(sim: Simulation) -> list[tuple[ChannelDef, Getter]]:
    r, v = sim.rider, sim.vehicle
    g = "Rider"
    return [
        (ChannelDef("throttle", "%", "Throttle", g), lambda: r.throttle),
        (ChannelDef("brake_front", "%", "Front brake lever", g), lambda: r.brake_front),
        (ChannelDef("brake_rear", "%", "Rear brake lever", g), lambda: r.brake_rear),
        (ChannelDef("steer", "deg", "Handlebar angle", g), lambda: r.steer),
        (ChannelDef("mode_request", "-", "Ride mode switch", g), lambda: float(r.mode_request)),
        (ChannelDef("gear", "-", "Gear", g), lambda: float(v.driveline.gear)),
        (ChannelDef("brake_pressure_front", "bar", "Front brake pressure", g),
         lambda: v.brakes.front_pressure),
        (ChannelDef("brake_pressure_rear", "bar", "Rear brake pressure", g),
         lambda: v.brakes.rear_pressure),
    ]


def _wheel(wheel: Wheel) -> list[tuple[ChannelDef, Getter]]:
    name, title = WHEEL_NAMES[wheel.index], WHEEL_TITLES[wheel.index]
    tyre = wheel.tyre
    g = "Wheels"
    return [
        (ChannelDef(f"load_{name}", "N", f"Wheel load, {title}", g), lambda: wheel.load),
        (ChannelDef(f"gap_{name}", "mm", f"Wheel lift height, {title}", g), lambda: wheel.gap),
        (ChannelDef(f"wheel_speed_{name}", "km/h", f"Wheel rim speed, {title}", g),
         lambda: wheel.omega * wheel.radius),
        (ChannelDef(f"slip_ratio_{name}", "%", f"Slip ratio, {title}", g), lambda: tyre.kappa),
        (ChannelDef(f"slip_angle_{name}", "deg", f"Slip angle, {title}", g),
         lambda: math.atan(tyre.tan_alpha)),
        (ChannelDef(f"fx_{name}", "N", f"Tyre force lengthwise, {title}", g), lambda: tyre.fx),
        (ChannelDef(f"fy_{name}", "N", f"Tyre force sideways, {title}", g), lambda: tyre.fy),
        (ChannelDef(f"torque_{name}", "Nm", f"Drive torque, {title}", g),
         lambda: wheel.drive_torque),
        (ChannelDef(f"friction_{name}", "Nm", f"Brake + rolling friction torque, {title}", g),
         lambda: wheel.friction_torque),
        (ChannelDef(f"steer_{name}", "deg", f"Wheel steering angle, {title}", g),
         lambda: wheel.steer),
        (ChannelDef(f"surface_{name}", "-", f"Surface number, {title}", g),
         lambda: float(SURFACE_NAMES.index(wheel.surface.name))),
    ]


def _motor(side: str, title: str, drive: ElectricDrive) -> list[tuple[ChannelDef, Getter]]:
    g = "Electric drive"
    return [
        (ChannelDef(f"motor_torque_{side}", "Nm", f"Motor torque, {title}", g),
         lambda: drive.torque),
        (ChannelDef(f"motor_current_{side}", "A", f"Motor battery current, {title}", g),
         lambda: drive.bus_current),
        (ChannelDef(f"motor_temp_{side}", "°C", f"Motor temperature, {title}", g),
         lambda: drive.temperature),
    ]


def _powertrain(sim: Simulation) -> list[tuple[ChannelDef, Getter]]:
    v = sim.vehicle
    b, e, d, ledger = v.battery, v.engine, v.driveline, v.energy
    left, right = v.drive_left, v.drive_right
    g = "Electric drive"
    channels = _motor("l", "left", left) + _motor("r", "right", right)
    channels += [
        (ChannelDef("battery_voltage", "V", "Battery voltage", g), lambda: b.voltage),
        (ChannelDef("battery_current", "A", "Battery current", g), lambda: b.current),
        (ChannelDef("battery_soc", "%", "Battery state of charge", g), lambda: b.soc),
        (ChannelDef("battery_temp", "°C", "Battery temperature", g), lambda: b.temperature),
        (ChannelDef("bms_connected", "-", "BMS connected (1) / tripped (0)", g),
         lambda: 1.0 if b.connected else 0.0),
        (ChannelDef("battery_energy", "Wh", "Battery energy used", g),
         lambda: ledger.battery_chemical),
        (ChannelDef("regen_energy", "Wh", "Energy recovered by regen", g),
         lambda: ledger.regen_energy),
    ]
    g = "Petrol drive"
    channels += [
        (ChannelDef("engine_speed", "rpm", "Engine speed", g), lambda: e.speed),
        (ChannelDef("engine_torque", "Nm", "Engine torque", g), lambda: e.torque),
        (ChannelDef("engine_throttle", "%", "Engine throttle", g), lambda: v.engine_throttle),
        (ChannelDef("engine_running", "-", "Engine running", g),
         lambda: 1.0 if e.running else 0.0),
        (ChannelDef("clutch_torque", "Nm", "Clutch torque", g), lambda: d.clutch_torque),
        (ChannelDef("fuel_used", "L", "Fuel used", g), lambda: e.fuel_used / e.fuel_density),
    ]
    return channels


def _controller(sim: Simulation) -> list[tuple[ChannelDef, Getter]]:
    o = sim.outputs
    g = "Controller"
    return [
        (ChannelDef("ctl_torque_left", "Nm", "Torque command, left", g), lambda: o.torque_left),
        (ChannelDef("ctl_torque_right", "Nm", "Torque command, right", g),
         lambda: o.torque_right),
        (ChannelDef("ctl_engine_throttle", "%", "Engine throttle command", g),
         lambda: o.engine_throttle),
        (ChannelDef("ctl_mode", "-", "Active ride mode", g), lambda: o.active_mode),
        (ChannelDef("ctl_speed_estimate", "km/h", "Controller speed estimate", g),
         lambda: o.diag_speed_estimate),
        (ChannelDef("ctl_traction_left", "%", "Traction control cut, left", g),
         lambda: o.diag_traction_left),
        (ChannelDef("ctl_traction_right", "%", "Traction control cut, right", g),
         lambda: o.diag_traction_right),
        (ChannelDef("ctl_vectoring_torque", "Nm", "Torque vectoring (left → right)", g),
         lambda: o.diag_vectoring_torque),
        (ChannelDef("ctl_regen_torque", "Nm", "Regen torque request per wheel", g),
         lambda: o.diag_regen_torque),
        (ChannelDef("ctl_power_limit", "%", "Power limit factor", g),
         lambda: o.diag_power_limit),
        (ChannelDef("ctl_stability_limit", "%", "Stability limit factor", g),
         lambda: o.diag_stability_limit),
    ]


def _sensors(sim: Simulation) -> list[tuple[ChannelDef, Getter]]:
    def reading(sensor: Sensor) -> Getter:
        return lambda: sensor.value

    return [(ChannelDef(f"sens_{spec.name}", spec.unit, f"Sensor: {spec.title}", "Sensors"),
             reading(sim.sensors.sensors[spec.name])) for spec in SENSOR_SPECS]


def build_channels(sim: Simulation) -> list[tuple[ChannelDef, Getter]]:
    """All channels with their getters for one simulation."""
    channels = _motion(sim) + _rider(sim)
    for wheel in sim.vehicle.wheels:
        channels += _wheel(wheel)
    return channels + _powertrain(sim) + _controller(sim) + _sensors(sim)
