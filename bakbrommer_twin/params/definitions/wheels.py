"""Parameters: wheels, suspension, tyres and road surfaces."""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Status

EST = Status.ESTIMATED

# Road surfaces known to the program, in the order shown in the UI.
# To add a surface: add a line to _SURFACE_DEFAULTS below. Nothing else.
# name: (peak friction, sliding/peak ratio, peak-slip scale, rolling resistance,
#        roughness height mm, roughness wavelength m)
_SURFACE_DEFAULTS: dict[str, tuple[float, float, float, float, float, float]] = {
    "dry_asphalt": (0.95, 0.80, 1.0, 0.015, 0.0, 3.0),
    "wet_asphalt": (0.65, 0.75, 1.0, 0.016, 0.0, 3.0),
    "gravel": (0.55, 0.95, 2.0, 0.030, 6.0, 1.0),
    "grass": (0.40, 0.90, 1.8, 0.060, 12.0, 2.0),
    "mud": (0.30, 0.95, 3.0, 0.120, 10.0, 3.0),
    "cobblestones": (0.60, 0.80, 1.2, 0.025, 4.0, 0.15),
}
SURFACE_NAMES: tuple[str, ...] = tuple(_SURFACE_DEFAULTS)
AXLES: tuple[str, ...] = ("front", "rear")


def register(reg: Registry) -> None:
    """Declare wheel, suspension, tyre and surface parameters."""
    _wheels(reg)
    _suspension(reg)
    _tyres(reg)
    _surfaces(reg)


def _wheels(reg: Registry) -> None:
    reg.category("wheels", "Wheels")
    reg.number("wheels.front_radius", 0.235, "m", 0.10, 0.45, "Front wheel radius",
               "Rolling radius of a front wheel (axle centre to ground, loaded).", EST)
    reg.number("wheels.rear_radius", 0.29, "m", 0.10, 0.45, "Rear wheel radius",
               "Rolling radius of the rear wheel (axle centre to ground, loaded).", EST)
    reg.number("wheels.front_inertia", 0.25, "kg·m²", 0.02, 3.0, "Front wheel inertia",
               "Rotational inertia of one front wheel including the hub motor rotor.", EST)
    reg.number("wheels.rear_inertia", 0.35, "kg·m²", 0.02, 3.0, "Rear wheel inertia",
               "Rotational inertia of the rear wheel including sprocket and brake.", EST)


def _suspension(reg: Registry) -> None:
    reg.category("suspension", "Suspension")
    for axle, stiffness, damping in (("front", 60.0, 1500.0), ("rear", 80.0, 2500.0)):
        reg.number(f"suspension.{axle}_stiffness", stiffness, "kN/m", 10.0, 500.0,
                   f"{axle.capitalize()} vertical stiffness per wheel",
                   "Combined vertical stiffness of tyre and suspension at one wheel. "
                   "A rigid frame on tyres only is roughly 150–200 kN/m.")
        reg.number(f"suspension.{axle}_damping", damping, "Ns/m", 50.0, 20000.0,
                   f"{axle.capitalize()} vertical damping per wheel",
                   "Combined vertical damping of tyre and suspension at one wheel.")


def _tyres(reg: Registry) -> None:
    reg.category("tyre", "Tyres")
    for axle, load in (("front", 800.0), ("rear", 1300.0)):
        title = axle.capitalize()
        reg.number(f"tyre.{axle}.slip_ratio_at_peak", 12.0, "%", 3.0, 40.0,
                   f"{title} slip ratio at peak grip",
                   "Wheel slip (drive or brake) at which the tyre gives its highest "
                   "lengthwise force on dry asphalt.")
        reg.number(f"tyre.{axle}.slip_angle_at_peak", 8.0, "deg", 2.0, 25.0,
                   f"{title} slip angle at peak grip",
                   "Slip angle at which the tyre gives its highest sideways force on "
                   "dry asphalt.")
        reg.number(f"tyre.{axle}.lateral_friction_ratio", 0.95, "-", 0.5, 1.3,
                   f"{title} sideways/lengthwise grip ratio",
                   "Peak sideways grip divided by peak lengthwise grip.")
        reg.number(f"tyre.{axle}.load_sensitivity", 0.15, "-", 0.0, 0.6,
                   f"{title} load sensitivity",
                   "How much the friction coefficient drops when the wheel load doubles "
                   "from the nominal load (0 = not at all).")
        reg.number(f"tyre.{axle}.nominal_load", load, "N", 100.0, 5000.0,
                   f"{title} nominal load",
                   "Wheel load at which the surface friction values apply exactly.", EST)
        reg.number(f"tyre.{axle}.relaxation_length_long", 0.10, "m", 0.02, 1.0,
                   f"{title} lengthwise relaxation length",
                   "Distance the wheel must roll before the lengthwise force has built up.")
        reg.number(f"tyre.{axle}.relaxation_length_lat", 0.25, "m", 0.05, 1.5,
                   f"{title} sideways relaxation length",
                   "Distance the wheel must roll before the sideways force has built up.")
    reg.number("tyre.low_speed_damping", 0.30, "s/m", 0.0, 2.0, "Low-speed slip damping",
               "Numerical damping of tyre force oscillations near standstill "
               "(extra slip per m/s of sliding speed; fades out with speed).")
    reg.number("tyre.low_speed_threshold", 2.0, "m/s", 0.2, 10.0, "Low-speed damping fade-out",
               "Speed above which the low-speed slip damping is switched off.")
    reg.number("tyre.slip_state_limit", 2.0, "-", 0.5, 10.0, "Slip state limit",
               "Largest slip value the tyre model keeps track of (numerical guard).")
    reg.number("tyre.rolling_resistance_scale", 1.0, "-", 0.3, 3.0, "Rolling resistance scale",
               "Multiplies the rolling resistance of every surface. Use it to match "
               "your tyres and pressure (calibration adjusts this).")
    reg.number("tyre.rolling_resistance_speed_factor", 1.5e-4, "s²/m²", 0.0, 2e-3,
               "Rolling resistance growth with speed",
               "Rolling resistance = base × (1 + factor × speed²).")


def _surfaces(reg: Registry) -> None:
    reg.category("surface", "Road surfaces")
    for name, (mu, ratio, scale, rolling, height, wavelength) in _SURFACE_DEFAULTS.items():
        title = name.replace("_", " ").capitalize()
        reg.number(f"surface.{name}.friction", mu, "-", 0.05, 1.5, f"{title}: peak friction",
                   "Highest friction coefficient between tyre and this surface.", EST)
        reg.number(f"surface.{name}.slide_ratio", ratio, "-", 0.5, 0.97,
                   f"{title}: sliding/peak ratio",
                   "Friction of a fully sliding tyre divided by the peak friction. "
                   "Loose surfaces are close to 1 (no clear peak).", EST)
        reg.number(f"surface.{name}.peak_slip_scale", scale, "-", 0.5, 5.0,
                   f"{title}: peak slip scale",
                   "How much more slip than on dry asphalt is needed to reach peak grip.", EST)
        reg.number(f"surface.{name}.rolling_resistance", rolling, "-", 0.003, 0.4,
                   f"{title}: rolling resistance",
                   "Rolling resistance coefficient (drag force / wheel load).", EST)
        reg.number(f"surface.{name}.roughness_height", height, "mm", 0.0, 80.0,
                   f"{title}: roughness height",
                   "Typical (RMS) height of bumps. 0 = perfectly smooth.", EST)
        reg.number(f"surface.{name}.roughness_wavelength", wavelength, "m", 0.05, 20.0,
                   f"{title}: roughness wavelength",
                   "Typical length of one bump.", EST)
