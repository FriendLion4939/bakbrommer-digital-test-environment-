"""Aerodynamic forces.

Drag and side force from the air speed relative to the vehicle:

    F_x = −½·ρ·Cd·A_front·|v_rel|·v_rel,x
    F_y = −½·ρ·Cs·A_side·|v_rel|·v_rel,y

(standard dynamic-pressure form; v_rel = vehicle velocity − wind velocity).
The forces act at the centre of pressure, which gives pitch, roll and yaw
moments about the centre of gravity. Units: N, Nm, m/s.
"""

from __future__ import annotations

import math

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.mass import MassProperties


def drag_area(params: ParamSet) -> float:
    """Cd × frontal area for the selected cargo box shape, m²."""
    shape = params.choice("aero.cargo_box_shape")
    return params.num(f"aero.cd_{shape}") * params.num("aero.frontal_area")


class Aero:
    """Air forces on the body. Call :meth:`update`; read the force/moment attributes."""

    __slots__ = ("arm_x", "arm_z", "drag_factor", "fx", "fy", "mx", "my", "mz", "power",
                 "side_factor")

    def __init__(self, params: ParamSet, props: MassProperties) -> None:
        density = params.num("environment.air_density")
        self.drag_factor = 0.5 * density * drag_area(params)  # N per (m/s)²
        self.side_factor = 0.5 * density * params.num("aero.cd_side") * params.num(
            "aero.side_area")
        # Centre of pressure relative to the CoG, body axes (x forward, z up).
        self.arm_z = params.num("aero.pressure_centre_height") - props.cog_height
        self.arm_x = props.cog_x - params.num("aero.pressure_centre_x")
        self.fx = self.fy = self.mx = self.my = self.mz = 0.0
        self.power = 0.0  # W dissipated by the air forces (≥ 0 in still air)

    def update(self, u: float, v: float, wind_x: float, wind_y: float) -> None:
        """Compute forces for body velocity (u, v) and wind velocity in body axes."""
        rel_x = u - wind_x
        rel_y = v - wind_y
        speed = math.sqrt(rel_x * rel_x + rel_y * rel_y)
        self.fx = -self.drag_factor * speed * rel_x
        self.fy = -self.side_factor * speed * rel_y
        # Moment of a force (F_x, F_y, 0) acting at (arm_x, 0, arm_z): M = r × F.
        self.mx = -self.arm_z * self.fy
        self.my = self.arm_z * self.fx
        self.mz = self.arm_x * self.fy
        self.power = -(self.fx * u + self.fy * v)
