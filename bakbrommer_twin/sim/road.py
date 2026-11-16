"""The road under the vehicle: surface per wheel, gradient, bumps and wind.

Each step :meth:`Road.update` looks up the route sample under the vehicle and
sets, for every wheel, the surface and the road height (roughness), and for
the whole vehicle the gradient and wind.

Roughness model: under each wheel the road height is a sum of a few sine
waves in the distance that wheel has rolled,

    z = a·Σ sin(φ_j),   dφ_j/ds = 2π/(λ·m_j)

with a = RMS height·√(2/N) (so the RMS of z equals the surface's roughness
height) and wavelengths spread around the surface's typical wavelength λ by
the fixed factors m_j. Each wheel has its own random start phases, so left
and right wheels see different bumps. Phases are integrated, so a change of
surface never makes the road jump. A real tyre rolls over small bumps more
softly than this point-contact model (no "enveloping").
"""

from __future__ import annotations

import math

import numpy as np

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.inputs import Environment
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.scenarios.route import Route

# Wavelengths of the sine components relative to the surface's typical wavelength.
_WAVELENGTH_FACTORS = (0.6, 1.0, 1.7, 2.9)
_AMPLITUDE_PER_RMS = math.sqrt(2.0 / len(_WAVELENGTH_FACTORS))


class Road:
    """Feeds the route's surface, gradient and bumps to the vehicle each step."""

    def __init__(self, params: ParamSet, route: Route, vehicle: Vehicle,
                 env: Environment) -> None:
        self.route = route
        self.vehicle = vehicle
        self.env = env
        surfaces = vehicle.surfaces
        self._surfaces = (
            [surfaces[name] for name in route.surface_left],
            [surfaces[name] for name in route.surface_right],
            [surfaces[name] for name in route.surface_center],
        )
        self._grade_sin = [g / math.sqrt(1.0 + g * g) for g in route.grade]
        self._grade_cos = [1.0 / math.sqrt(1.0 + g * g) for g in route.grade]
        # How many route samples each wheel is ahead (+) or behind (−) the CoG.
        self._offsets = [round(wheel.base_x / route.spacing) for wheel in vehicle.wheels]
        self._last = len(route) - 1
        rng = np.random.default_rng(params.integer("sim.random_seed"))
        self._phases: list[list[float]] = rng.uniform(
            0.0, 2.0 * math.pi, (len(vehicle.wheels), len(_WAVELENGTH_FACTORS))).tolist()
        self._amplitude = [0.0] * len(vehicle.wheels)  # present bump amplitude per wheel, m
        # Wind blows *from* the given direction (0 = from straight ahead at the start).
        speed = params.num("environment.wind_speed")
        direction = params.num("environment.wind_direction")
        env.wind_x = -speed * math.cos(direction)
        env.wind_y = -speed * math.sin(direction)

    def update(self, dt: float, route_index: int) -> None:
        """Set surface, road height, gradient for the present position."""
        env = self.env
        env.grade_sin = self._grade_sin[route_index]
        env.grade_cos = self._grade_cos[route_index]
        env.route_heading = self.route.heading[route_index]
        last = self._last
        for wheel in self.vehicle.wheels:
            i = wheel.index
            sample = route_index + self._offsets[i]
            sample = 0 if sample < 0 else (last if sample > last else sample)
            surface = self._surfaces[i][sample]
            wheel.surface = surface
            target = surface.roughness_height * _AMPLITUDE_PER_RMS
            amplitude = self._amplitude[i]
            if target == 0.0 and amplitude == 0.0:
                wheel.ground = wheel.ground_rate = 0.0
                continue
            travel = wheel.v_long * dt  # distance rolled this step, m
            wavelength = surface.roughness_wavelength
            # Fade the amplitude over one wavelength when the surface changes.
            amplitude += (target - amplitude) * min(1.0, abs(travel) / wavelength)
            self._amplitude[i] = amplitude
            phases = self._phases[i]
            height = slope = 0.0
            for j, factor in enumerate(_WAVELENGTH_FACTORS):
                wave_number = 2.0 * math.pi / (wavelength * factor)  # rad/m
                phase = phases[j] + wave_number * travel
                phases[j] = phase
                height += math.sin(phase)
                slope += wave_number * math.cos(phase)
            wheel.ground = amplitude * height
            wheel.ground_rate = amplitude * slope * wheel.v_long
