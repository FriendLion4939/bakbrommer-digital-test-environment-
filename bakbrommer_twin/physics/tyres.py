"""Tyre force model: simplified magic formula with combined slip and relaxation.

Model
-----
* Slip ratio κ = (r·ω − V_x)/|V_x| and slip angle tan α = −V_y/|V_x| are not
  used directly. Each tyre keeps two *relaxed* slip states that follow the
  kinematic slip with a first-order lag over the relaxation length σ
  (Pacejka, "Tyre and Vehicle Dynamics", 2nd ed., §7.2.3):
      σ_x·dκ'/dt + |V_x|·κ' = r·ω − V_x
      σ_y·d(tan α')/dt + |V_x|·tan α' = −V_y
  At standstill these act as springs (tyre deflection), so a parked vehicle
  is held in place and nothing divides by zero.
* Near standstill a damping term proportional to the sliding speed is added
  to the slips and fades out with speed (Pacejka §8.6).
* Combined slip uses normalised slips s_x = κ'/κ_peak, s_y = tan α'/tan α_peak
  and s = √(s_x² + s_y²). The force magnitude follows the magic formula
      F/(μ·F_z) = sin(C·atan(B·s))
  and is shared between the directions in proportion to s_x and s_y (friction
  ellipse). C and B come from the surface (see ``surfaces.py``).
* Load sensitivity: μ_eff = μ / (1 + k·(F_z/F_z,nom − 1)).

All quantities are SI: forces N, speeds m/s, slips dimensionless.
"""

from __future__ import annotations

import math

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.surfaces import Surface

_TINY_SLIP = 1e-9  # below this the force curve is treated as its straight start


class Tyre:
    """One tyre. Call :meth:`update` every step; read ``fx``, ``fy`` afterwards."""

    __slots__ = ("damping", "damping_gain", "fx", "fy", "kappa", "kappa_peak", "lat_ratio",
                 "load_sensitivity", "low_speed", "nominal_load", "secant_stiffness",
                 "sigma_lat", "sigma_long", "slip_limit", "tan_alpha", "tan_alpha_peak")

    def __init__(self, params: ParamSet, axle: str) -> None:
        self.kappa_peak = params.num(f"tyre.{axle}.slip_ratio_at_peak")
        self.tan_alpha_peak = math.tan(params.num(f"tyre.{axle}.slip_angle_at_peak"))
        self.lat_ratio = params.num(f"tyre.{axle}.lateral_friction_ratio")
        self.load_sensitivity = params.num(f"tyre.{axle}.load_sensitivity")
        self.nominal_load = params.num(f"tyre.{axle}.nominal_load")
        self.sigma_long = params.num(f"tyre.{axle}.relaxation_length_long")
        self.sigma_lat = params.num(f"tyre.{axle}.relaxation_length_lat")
        self.damping_gain = params.num("tyre.low_speed_damping")
        self.low_speed = params.num("tyre.low_speed_threshold")
        self.slip_limit = params.num("tyre.slip_state_limit")
        self.kappa = 0.0  # relaxed slip ratio κ', -
        self.tan_alpha = 0.0  # relaxed tan(slip angle), -
        self.fx = 0.0  # lengthwise force on the vehicle, N (+ = forwards)
        self.fy = 0.0  # sideways force on the vehicle, N (+ = to the wheel's left)
        self.secant_stiffness = 0.0  # F_x/κ, N — used for the implicit wheel update
        self.damping = 0.0  # active low-speed damping, slip per (m/s)

    def update(self, dt: float, v_long: float, v_lat: float, rim_speed: float,
               load: float, surface: Surface) -> None:
        """Advance the slip states by ``dt`` and compute the forces.

        ``v_long``/``v_lat``: speed of the contact point along/across the wheel
        (m/s). ``rim_speed`` = r·ω (m/s). ``load`` = vertical force F_z (N).
        """
        if load <= 0.0:  # wheel in the air: no force, slip memory is lost
            self.kappa = self.tan_alpha = self.fx = self.fy = 0.0
            self.secant_stiffness = self.damping = 0.0
            return
        abs_v = abs(v_long)
        slide = rim_speed - v_long  # lengthwise sliding speed, m/s
        limit = self.slip_limit

        # Relaxation equations, discretised implicitly in the decay term so the
        # update is stable at any speed: κ'⁺ = (κ' + dt·slide/σ)/(1 + dt·|V|/σ).
        kappa = (self.kappa + dt * slide / self.sigma_long) / (1.0 + dt * abs_v / self.sigma_long)
        kappa = limit if kappa > limit else (-limit if kappa < -limit else kappa)
        tan_alpha = ((self.tan_alpha - dt * v_lat / self.sigma_lat)
                     / (1.0 + dt * abs_v / self.sigma_lat))
        tan_alpha = limit if tan_alpha > limit else (-limit if tan_alpha < -limit else tan_alpha)
        self.kappa = kappa
        self.tan_alpha = tan_alpha

        # Low-speed damping: extra slip proportional to sliding speed, linear fade-out.
        fade = 1.0 - abs_v / self.low_speed
        if fade > 0.0:
            damping = self.damping_gain * fade
            kappa += damping * slide
            tan_alpha -= damping * v_lat
        else:
            damping = 0.0
        self.damping = damping

        mu = surface.friction / (1.0 + self.load_sensitivity * (load / self.nominal_load - 1.0))
        kappa_peak = self.kappa_peak * surface.peak_slip_scale
        s_x = kappa / kappa_peak
        s_y = tan_alpha / (self.tan_alpha_peak * surface.peak_slip_scale)
        s = math.sqrt(s_x * s_x + s_y * s_y)
        if s < _TINY_SLIP:
            force_per_slip = surface.stiffness * surface.shape  # slope of sin(C·atan(B·s)) at 0
        else:
            force_per_slip = math.sin(surface.shape * math.atan(surface.stiffness * s)) / s
        base = mu * load * force_per_slip  # N per unit of normalised slip
        self.fx = base * s_x
        self.fy = base * self.lat_ratio * s_y
        self.secant_stiffness = base / kappa_peak

    def reset(self) -> None:
        """Forget all slip (used when placing the vehicle at its start)."""
        self.kappa = self.tan_alpha = self.fx = self.fy = 0.0
        self.secant_stiffness = self.damping = 0.0


def force_curve(surface: Surface, normalised_slip: float) -> float:
    """F/(μ·F_z) of the magic formula for a pure slip (for plots and tests)."""
    return math.sin(surface.shape * math.atan(surface.stiffness * normalised_slip))
