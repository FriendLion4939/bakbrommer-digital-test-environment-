"""Road surfaces: grip, rolling resistance and roughness of each surface type."""

from __future__ import annotations

import math

from bakbrommer_twin.params.definitions.wheels import SURFACE_NAMES
from bakbrommer_twin.params.paramset import ParamSet


class Surface:
    """Properties of one road surface, ready for the tyre model."""

    __slots__ = ("friction", "name", "peak_slip_scale", "rolling_resistance",
                 "roughness_height", "roughness_wavelength", "shape", "stiffness")

    def __init__(self, params: ParamSet, name: str) -> None:
        self.name = name
        self.friction = params.num(f"surface.{name}.friction")
        self.peak_slip_scale = params.num(f"surface.{name}.peak_slip_scale")
        self.rolling_resistance = (params.num(f"surface.{name}.rolling_resistance")
                                   * params.num("tyre.rolling_resistance_scale"))
        self.roughness_height = params.num(f"surface.{name}.roughness_height")
        self.roughness_wavelength = params.num(f"surface.{name}.roughness_wavelength")
        # Magic formula F/F_peak = sin(C·atan(B·s)) with s = slip / slip-at-peak.
        # Far beyond the peak the curve tends to sin(C·π/2), which must equal the
        # sliding/peak ratio  ->  C = 2 − (2/π)·asin(ratio).
        # The peak (sin = 1) must sit at s = 1  ->  B = tan(π/(2·C)).
        ratio = params.num(f"surface.{name}.slide_ratio")
        self.shape = 2.0 - (2.0 / math.pi) * math.asin(ratio)  # C, -
        self.stiffness = math.tan(math.pi / (2.0 * self.shape))  # B, -


def load_surfaces(params: ParamSet) -> dict[str, Surface]:
    """All surfaces by name."""
    return {name: Surface(params, name) for name in SURFACE_NAMES}
