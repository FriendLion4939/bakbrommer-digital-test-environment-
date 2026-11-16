"""Chassis: one rigid body with six degrees of freedom on three wheels.

Frames
------
* World frame: X, Y in the road plane, Z along the road normal (up).
  A gradient is modelled by tilting gravity, not the road.
* Level frame: the world frame turned by the yaw angle ψ (x points where
  the vehicle heads, z is the road normal).
* Body frame: origin at the centre of gravity, x forward, y left, z up.
  Orientation by yaw ψ, pitch θ, roll φ (Z-Y-X Euler angles, right-handed:
  positive pitch = nose down, positive roll = left side up).

Rotation body → level frame, R = R_y(θ)·R_x(φ):

    | cθ   sθ·sφ   sθ·cφ |
    | 0    cφ      −sφ   |
    | −sθ  cθ·sφ   cθ·cφ |

Equations of motion (Newton–Euler in the rotating body frame, principal
axes; e.g. Greenwood, "Principles of Dynamics", ch. 8):

    m·(du/dt + q·w − r·v) = F_x        I_xx·dp/dt + (I_zz − I_yy)·q·r = M_x
    m·(dv/dt + r·u − p·w) = F_y        I_yy·dq/dt + (I_xx − I_zz)·r·p = M_y
    m·(dw/dt + p·v − q·u) = F_z        I_zz·dr/dt + (I_yy − I_xx)·p·q = M_z

Euler angle rates:  dφ/dt = p + (q·sφ + r·cφ)·tanθ,  dθ/dt = q·cφ − r·sφ,
dψ/dt = (q·sφ + r·cφ)/cθ.

Wheel contact: each wheel is a vertical spring-damper along the road normal
that can only push: F_z = max(0, k·δ + c·dδ/dt) while the compression δ > 0.
A wheel whose spring is fully extended carries no load — it has lifted.

Integration: semi-implicit Euler (velocities from forces first, then
positions from the new velocities).
"""

from __future__ import annotations

import math

from bakbrommer_twin.physics.aero import Aero
from bakbrommer_twin.physics.mass import MassProperties
from bakbrommer_twin.physics.wheels import Wheel


class Chassis:
    """Rigid-body state of the vehicle and its equations of motion."""

    __slots__ = (
        "accel_x", "accel_y", "accel_z", "damper_power", "gravity_power", "impulse_x",
        "impulse_y", "ixx", "iyy", "izz", "mass", "p", "pitch", "q", "r", "r00", "r01",
        "r02", "r11", "r12", "r20", "r21", "r22", "roll", "u", "v", "w", "x", "y", "yaw", "z",
    )

    def __init__(self, props: MassProperties) -> None:
        self.mass = props.mass
        self.ixx = props.inertia_roll
        self.iyy = props.inertia_pitch
        self.izz = props.inertia_yaw
        self.x = self.y = 0.0  # world position of the CoG, m
        self.z = props.cog_height  # height of the CoG above the road plane, m
        self.yaw = self.pitch = self.roll = 0.0  # rad
        self.u = self.v = self.w = 0.0  # CoG velocity in body axes, m/s
        self.p = self.q = self.r = 0.0  # angular velocity in body axes, rad/s
        self.r00 = self.r11 = self.r22 = 1.0
        self.r01 = self.r02 = self.r12 = self.r20 = self.r21 = 0.0
        # What an accelerometer at the CoG measures (specific force), body axes, m/s².
        self.accel_x = self.accel_y = 0.0
        self.accel_z = 0.0
        self.damper_power = 0.0  # W dissipated in the vertical dampers
        self.gravity_power = 0.0  # W of work done by gravity
        self.impulse_x = self.impulse_y = 0.0  # ∫ΣF dt in world axes, N·s (for tests)

    def update_rotation(self) -> None:
        """Refresh the rotation matrix from the present pitch and roll."""
        cos_t, sin_t = math.cos(self.pitch), math.sin(self.pitch)
        cos_f, sin_f = math.cos(self.roll), math.sin(self.roll)
        self.r00 = cos_t
        self.r01 = sin_t * sin_f
        self.r02 = sin_t * cos_f
        self.r11 = cos_f
        self.r12 = -sin_f
        self.r20 = -sin_t
        self.r21 = cos_t * sin_f
        self.r22 = cos_t * cos_f

    def contacts(self, wheels: list[Wheel]) -> None:
        """Compute load, lift gap and contact-point velocities of every wheel."""
        u, v, w, p, q, r = self.u, self.v, self.w, self.p, self.q, self.r
        r00, r01, r02, r11, r12 = self.r00, self.r01, self.r02, self.r11, self.r12
        r20, r21, r22 = self.r20, self.r21, self.r22
        z = self.z
        damper_power = 0.0
        for wheel in wheels:
            # Height of the unloaded tyre bottom above the road plane.
            foot_height = z + r20 * wheel.x + r21 * wheel.y + r22 * wheel.z_foot
            compression = wheel.ground - foot_height
            if compression < 0.0:
                wheel.gap = -compression
                compression = 0.0
            else:
                wheel.gap = 0.0
            wheel.compression = compression
            # Contact point = foot moved up along the road normal by the compression
            # (the road normal in body axes is the third row of R).
            cx = wheel.x + compression * r20
            cy = wheel.y + compression * r21
            cz = wheel.z_foot + compression * r22
            wheel.contact_x, wheel.contact_y, wheel.contact_z = cx, cy, cz
            # Velocity of that point: v + ω × c (body axes), then to the level frame.
            vbx = u + q * cz - r * cy
            vby = v + r * cx - p * cz
            vbz = w + p * cy - q * cx
            vlx = r00 * vbx + r01 * vby + r02 * vbz
            vly = r11 * vby + r12 * vbz
            vlz = r20 * vbx + r21 * vby + r22 * vbz
            if wheel.gap > 0.0:
                load = 0.0
            else:
                closing = wheel.ground_rate - vlz  # dδ/dt, m/s
                damper = wheel.damping * closing
                load = wheel.stiffness * compression + damper
                if load < 0.0:
                    load = 0.0  # the road cannot pull the tyre down
                else:
                    damper_power += damper * closing
            wheel.load = load
            # Wheel heading: body x axis turned by the steering angle, projected
            # on the road plane and normalised.
            hx = r00 * wheel.cos_steer + r01 * wheel.sin_steer
            hy = r11 * wheel.sin_steer
            norm = math.sqrt(hx * hx + hy * hy)
            hx /= norm
            hy /= norm
            wheel.dir_x, wheel.dir_y = hx, hy
            wheel.v_long = vlx * hx + vly * hy
            wheel.v_lat = vly * hx - vlx * hy
        self.damper_power = damper_power

    def integrate(self, dt: float, wheels: list[Wheel], gravity_x: float, gravity_y: float,
                  gravity_z: float, aero: Aero) -> None:
        """Sum all forces and advance the body state by ``dt``.

        ``gravity_*`` is the gravity acceleration vector in the level frame.
        """
        r00, r01, r02, r11, r12 = self.r00, self.r01, self.r02, self.r11, self.r12
        r20, r21, r22 = self.r20, self.r21, self.r22
        # Contact forces (body axes) and their moments about the CoG.
        fx = fy = fz = mx = my = mz = 0.0
        for wheel in wheels:
            load = wheel.load
            if load <= 0.0:
                continue
            tyre = wheel.tyre
            flx = tyre.fx * wheel.dir_x - tyre.fy * wheel.dir_y  # level frame
            fly = tyre.fx * wheel.dir_y + tyre.fy * wheel.dir_x
            bx = r00 * flx + r20 * load  # body axes: Rᵀ·F_level
            by = r01 * flx + r11 * fly + r21 * load
            bz = r02 * flx + r12 * fly + r22 * load
            fx += bx
            fy += by
            fz += bz
            cx, cy, cz = wheel.contact_x, wheel.contact_y, wheel.contact_z
            mx += cy * bz - cz * by  # M = c × F
            my += cz * bx - cx * bz
            mz += cx * by - cy * bx
        fx += aero.fx
        fy += aero.fy
        mx += aero.mx
        my += aero.my
        mz += aero.mz
        mass = self.mass
        # An accelerometer feels every force except gravity.
        self.accel_x, self.accel_y, self.accel_z = fx / mass, fy / mass, fz / mass
        # Gravity, level frame → body axes.
        gbx = r00 * gravity_x + r20 * gravity_z
        gby = r01 * gravity_x + r11 * gravity_y + r21 * gravity_z
        gbz = r02 * gravity_x + r12 * gravity_y + r22 * gravity_z
        u, v, w, p, q, r = self.u, self.v, self.w, self.p, self.q, self.r
        self.gravity_power = mass * (gbx * u + gby * v + gbz * w)
        ax = fx / mass + gbx
        ay = fy / mass + gby
        az = fz / mass + gbz

        # Newton–Euler in the rotating body frame.
        self.u = u + dt * (ax - (q * w - r * v))
        self.v = v + dt * (ay - (r * u - p * w))
        self.w = w + dt * (az - (p * v - q * u))
        ixx, iyy, izz = self.ixx, self.iyy, self.izz
        self.p = p + dt * (mx - (izz - iyy) * q * r) / ixx
        self.q = q + dt * (my - (ixx - izz) * r * p) / iyy
        self.r = r + dt * (mz - (iyy - ixx) * p * q) / izz

        # Positions from the new velocities (semi-implicit Euler).
        u, v, w, p, q, r = self.u, self.v, self.w, self.p, self.q, self.r
        cos_f, sin_f = r11, -r12
        cos_t = r00
        tan_t = -r20 / cos_t
        yaw_rate = (q * sin_f + r * cos_f) / cos_t
        self.roll += dt * (p + (q * sin_f + r * cos_f) * tan_t)
        self.pitch += dt * (q * cos_f - r * sin_f)
        vlx = r00 * u + r01 * v + r02 * w
        vly = r11 * v + r12 * w
        vlz = r20 * u + r21 * v + r22 * w
        cos_y, sin_y = math.cos(self.yaw), math.sin(self.yaw)
        self.x += dt * (cos_y * vlx - sin_y * vly)
        self.y += dt * (sin_y * vlx + cos_y * vly)
        self.z += dt * vlz
        self.yaw += dt * yaw_rate
        # Impulse of all forces in world axes (momentum check in the tests).
        level_x = mass * (r00 * ax + r01 * ay + r02 * az)
        level_y = mass * (r11 * ay + r12 * az)
        self.impulse_x += dt * (cos_y * level_x - sin_y * level_y)
        self.impulse_y += dt * (sin_y * level_x + cos_y * level_y)

    def kinetic_energy(self) -> float:
        """Translational + rotational kinetic energy of the body, J."""
        return 0.5 * (
            self.mass * (self.u * self.u + self.v * self.v + self.w * self.w)
            + self.ixx * self.p * self.p + self.iyy * self.q * self.q
            + self.izz * self.r * self.r)

    def world_velocity(self) -> tuple[float, float]:
        """Velocity of the CoG in world axes (X, Y), m/s."""
        vlx = self.r00 * self.u + self.r01 * self.v + self.r02 * self.w
        vly = self.r11 * self.v + self.r12 * self.w
        cos_y, sin_y = math.cos(self.yaw), math.sin(self.yaw)
        return cos_y * vlx - sin_y * vly, sin_y * vlx + cos_y * vly

    def yaw_rate(self) -> float:
        """Rate of change of the heading angle, rad/s."""
        return (self.q * -self.r12 + self.r * self.r11) / self.r00
