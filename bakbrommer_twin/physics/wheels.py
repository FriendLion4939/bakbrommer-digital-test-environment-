"""One wheel: geometry, spin speed, contact results and friction handling.

Wheel order everywhere: index 0 = front-left, 1 = front-right, 2 = rear.

Spin dynamics (front wheels; the rear wheel is advanced by the driveline
solver because it is coupled to the engine):

    I·dω/dt = T_drive − r·F_x − T_friction

``T_friction`` (brake + rolling resistance + motor drag) is dry friction: it
takes exactly the value that stops the wheel, limited to its capacity. This
"friction as a constraint" update is unconditionally stable and holds a
braked wheel exactly still (docs/PHYSICS.md).

The low-speed slip damping of the tyre makes F_x depend on ω within the
step: ∂F_x/∂ω = (F_x/κ)·damping·r. Treating that term implicitly is the
same as using the inertia I + dt·r²·(F_x/κ)·damping in the update.
"""

from __future__ import annotations

from bakbrommer_twin.physics.surfaces import Surface
from bakbrommer_twin.physics.tyres import Tyre

WHEEL_NAMES: tuple[str, ...] = ("fl", "fr", "r")
FRONT_LEFT, FRONT_RIGHT, REAR = 0, 1, 2


class Wheel:
    """State and per-step results of one wheel (plain attributes for speed)."""

    __slots__ = (
        "base_x", "base_y", "compression", "contact_x", "contact_y", "contact_z",
        "cos_steer", "damping", "dir_x", "dir_y", "drive_torque", "friction_capacity",
        "friction_torque", "gap", "ground", "index", "inertia", "load",
        "omega", "radius", "sin_steer", "static_load", "steer", "stiffness", "surface",
        "tyre", "v_lat", "v_long", "x", "y", "z_foot",
    )

    def __init__(self, index: int, radius: float, inertia: float, stiffness: float,
                 damping: float, tyre: Tyre, surface: Surface) -> None:
        self.index = index
        self.radius = radius  # m
        self.inertia = inertia  # kg·m²
        self.stiffness = stiffness  # N/m, vertical (tyre + suspension)
        self.damping = damping  # Ns/m, vertical
        self.tyre = tyre
        self.surface = surface  # surface under this wheel right now
        # Position of the unloaded tyre bottom ("foot") in body axes, m.
        self.base_x = self.base_y = 0.0  # straight-ahead position
        self.x = self.y = self.z_foot = 0.0  # present position (moves with centre-pivot)
        self.steer = 0.0  # steering angle of this wheel, rad (+ = left)
        self.cos_steer = 1.0
        self.sin_steer = 0.0
        self.static_load = 0.0  # N at rest on level ground
        self.omega = 0.0  # spin speed, rad/s (+ = rolling forwards)
        self.ground = 0.0  # road height under the wheel (set by the road model), m
        # Contact results of this step (set by the chassis).
        self.compression = 0.0  # m of spring compression (0 when lifted)
        self.gap = 0.0  # m between tyre and road when lifted
        self.load = 0.0  # vertical force F_z, N
        self.v_long = 0.0  # contact point speed along the wheel, m/s
        self.v_lat = 0.0  # contact point speed across the wheel, m/s
        self.dir_x = 1.0  # wheel heading in the level frame (unit vector)
        self.dir_y = 0.0
        self.contact_x = self.contact_y = self.contact_z = 0.0  # contact point, body axes
        # Torques of this step.
        self.drive_torque = 0.0  # Nm from motor (front) or clutch (rear)
        self.friction_capacity = 0.0  # Nm the friction can hold at most
        self.friction_torque = 0.0  # Nm actually applied (signed, opposes rotation)

    def effective_inertia(self, dt: float) -> float:
        """Inertia including the implicit low-speed tyre damping term, kg·m²."""
        tyre = self.tyre
        return self.inertia + dt * self.radius * self.radius * (
            tyre.secant_stiffness * tyre.damping)

    def spin(self, dt: float) -> None:
        """Advance the spin speed of a wheel that is not coupled to the engine."""
        inertia = self.effective_inertia(dt)
        free = self.omega + dt * (self.drive_torque - self.radius * self.tyre.fx) / inertia
        capacity = self.friction_capacity
        stop = inertia * free / dt  # friction torque that would stop the wheel this step
        if stop > capacity:
            self.friction_torque = capacity
            self.omega = free - dt * capacity / inertia
        elif stop < -capacity:
            self.friction_torque = -capacity
            self.omega = free + dt * capacity / inertia
        else:  # friction is strong enough: the wheel stands exactly still
            self.friction_torque = stop
            self.omega = 0.0
