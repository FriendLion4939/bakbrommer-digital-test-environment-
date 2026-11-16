"""Parameters: the simulated rider (driver model)."""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry


def register(reg: Registry) -> None:
    """Declare driver-model parameters."""
    reg.category("driver", "Driver model")
    reg.number("driver.update_rate", 100.0, "Hz", 5.0, 1000.0, "Reaction rate",
               "How often the simulated rider updates throttle, brakes and steering.")
    reg.number("driver.max_lateral_accel", 2.5, "m/s²", 0.5, 12.0, "Cornering limit",
               "The rider slows down so corners are taken at no more than this "
               "sideways acceleration. Raise it for sporty riding.")
    reg.number("driver.max_deceleration", 3.0, "m/s²", 0.5, 10.0, "Planned braking",
               "Deceleration the rider plans with when slowing for a corner or a stop.")
    reg.number("driver.preview_time", 0.7, "s", 0.1, 3.0, "Steering preview time",
               "How far ahead (in seconds of travel) the rider aims on the route.")
    reg.number("driver.min_preview_distance", 2.5, "m", 0.5, 20.0, "Shortest preview distance",
               "The rider never aims at a point closer than this.")
    reg.number("driver.speed_gain", 0.5, "s/m", 0.02, 5.0, "Speed control gain",
               "Throttle (or brake) applied per m/s of speed error.")
    reg.number("driver.speed_integral_gain", 0.15, "1/m", 0.0, 2.0, "Speed control memory",
               "How quickly the rider adds throttle when a speed error persists.")
    reg.number("driver.full_brake_deceleration", 6.0, "m/s²", 1.0, 12.0,
               "Deceleration expected at full brake",
               "Used to decide how hard to pull the lever for a planned deceleration.")
    reg.number("driver.rear_brake_ratio", 0.6, "-", 0.0, 1.5, "Rear brake use",
               "Rear lever position as a share of the front lever position.")
    reg.number("driver.steer_rate_limit", 360.0, "deg/s", 30.0, 2000.0, "Fastest steering",
               "Quickest the rider can turn the handlebar.")
    reg.number("driver.upshift_speed", 7000.0, "rpm", 2500.0, 12000.0, "Upshift engine speed",
               "The rider shifts up above this engine speed (manual gearbox).")
    reg.number("driver.downshift_speed", 3300.0, "rpm", 1000.0, 8000.0, "Downshift engine speed",
               "The rider shifts down below this engine speed (manual gearbox).")
