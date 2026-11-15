"""Mass properties of the whole vehicle, built up from its components.

The vehicle is the sum of five components (chassis, battery, rider, cargo,
fuel). From their masses and positions this module computes total mass,
centre of gravity (CoG) and rotational inertia about the CoG. Because cargo is
a component, the CoG moves when the load changes.

Frames
------
Design frame (parameters): origin on the ground under the middle of the front
axle, ``x`` backwards, ``y`` left, ``height`` up.
Body frame (physics): origin at the CoG, ``x`` forwards, ``y`` left, ``z`` up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bakbrommer_twin.params.paramset import ParamSet

GRAVITY = 9.80665  # m/s², standard gravity (physical constant, not a parameter)

COMPONENTS = ("chassis", "battery", "rider", "cargo", "fuel")


@dataclass(frozen=True)
class MassProperties:
    """Total mass, CoG position (design frame) and inertia about the CoG."""

    mass: float  # kg
    cog_x: float  # m behind the front axle
    cog_y: float  # m left of the centre line
    cog_height: float  # m above the ground
    inertia_roll: float  # kg·m² about the body x axis through the CoG
    inertia_pitch: float  # kg·m² about the body y axis through the CoG
    inertia_yaw: float  # kg·m² about the body z axis through the CoG


def _own_inertia(params: ParamSet, key: str, mass: float) -> tuple[float, float, float]:
    """Inertia of one component about its own centre: (roll, pitch, yaw), kg·m²."""
    if key == "chassis":
        # I = m·k² with k the radius of gyration (definition of gyradius).
        return (
            mass * params.num("mass.chassis.gyradius_roll") ** 2,
            mass * params.num("mass.chassis.gyradius_pitch") ** 2,
            mass * params.num("mass.chassis.gyradius_yaw") ** 2,
        )
    if key == "rider":
        inertia = mass * params.num("mass.rider.gyradius") ** 2
        return inertia, inertia, inertia
    if key == "cargo":
        # Solid box: I_axis = m/12·(a² + b²), a and b the sides perpendicular to the axis.
        length = params.num("mass.cargo.length")
        width = params.num("mass.cargo.width")
        height = params.num("mass.cargo.stack_height")
        return (
            mass / 12.0 * (width**2 + height**2),
            mass / 12.0 * (length**2 + height**2),
            mass / 12.0 * (length**2 + width**2),
        )
    return 0.0, 0.0, 0.0  # battery and fuel are treated as point masses


def mass_properties(params: ParamSet) -> MassProperties:
    """Combine all components into total mass, CoG and inertia.

    CoG = Σ(mᵢ·rᵢ)/Σmᵢ. Inertia uses the parallel-axis theorem:
    I = Σ(Iᵢ,own + mᵢ·dᵢ²), dᵢ = distance of the component from the axis
    through the combined CoG. Products of inertia are neglected.
    """
    parts = [
        (
            key,
            params.num(f"mass.{key}.mass"),
            params.num(f"mass.{key}.x"),
            params.num(f"mass.{key}.y"),
            params.num(f"mass.{key}.height"),
        )
        for key in COMPONENTS
    ]
    total = sum(m for _, m, _, _, _ in parts)
    if total <= 0.0:
        raise ValueError("Total vehicle mass must be greater than zero")
    cog_x = sum(m * x for _, m, x, _, _ in parts) / total
    cog_y = sum(m * y for _, m, _, y, _ in parts) / total
    cog_h = sum(m * h for _, m, _, _, h in parts) / total

    roll = pitch = yaw = 0.0
    for key, m, x, y, h in parts:
        own_roll, own_pitch, own_yaw = _own_inertia(params, key, m)
        dx, dy, dz = x - cog_x, y - cog_y, h - cog_h
        roll += own_roll + m * (dy**2 + dz**2)
        pitch += own_pitch + m * (dx**2 + dz**2)
        yaw += own_yaw + m * (dx**2 + dy**2)
    return MassProperties(total, cog_x, cog_y, cog_h, roll, pitch, yaw)


def static_wheel_loads(params: ParamSet) -> tuple[float, float, float]:
    """Vertical load on (front-left, front-right, rear) at rest on level ground, N.

    Three wheels make the problem statically determinate:
    ΣF_z = m·g, pitch moment balance about the front axle gives the rear
    load F_r = m·g·x_cog/L, and roll moment balance about the centre line
    gives F_fl − F_fr = m·g·y_cog/(t/2).
    """
    props = mass_properties(params)
    wheelbase = params.num("geometry.wheelbase")
    half_track = params.num("geometry.front_track") / 2.0
    weight = props.mass * GRAVITY
    rear = weight * props.cog_x / wheelbase
    front_total = weight - rear
    difference = weight * props.cog_y / half_track
    return (front_total + difference) / 2.0, (front_total - difference) / 2.0, rear


def lift_threshold_accel(params: ParamSet, turn_left: bool) -> float:
    """Steady lateral acceleration at which the inner front wheel lifts, m/s².

    The vehicle tips about the line from the outer front tyre to the rear
    tyre. Moment balance about that line (rigid vehicle, level road, constant
    speed): a_y = g·[(t/2)·(1 − x_cog/L) ± y_cog] / h_cog.
    In a left turn the vehicle tips over the right wheel, so a CoG offset to
    the left (+y) helps; in a right turn it hurts.
    """
    props = mass_properties(params)
    wheelbase = params.num("geometry.wheelbase")
    half_track = params.num("geometry.front_track") / 2.0
    lever = half_track * (1.0 - props.cog_x / wheelbase)
    lever += props.cog_y if turn_left else -props.cog_y
    return max(0.0, GRAVITY * lever / props.cog_height)


def tip_over_angle(params: ParamSet) -> float:
    """Roll angle at which the CoG is above the tipping line (worst side), rad.

    tan(angle) = d/h with d the horizontal distance from the CoG to the line
    through the outer front tyre and the rear tyre.
    """
    props = mass_properties(params)
    wheelbase = params.num("geometry.wheelbase")
    half_track = params.num("geometry.front_track") / 2.0
    axis_length = math.hypot(wheelbase, half_track)
    lever = (wheelbase - props.cog_x) * half_track - abs(props.cog_y) * wheelbase
    distance = max(0.0, lever / axis_length)
    return math.atan2(distance, props.cog_height)
