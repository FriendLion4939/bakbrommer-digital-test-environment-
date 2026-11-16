"""Parameters: simulation settings and safety thresholds."""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry


def register(reg: Registry) -> None:
    """Declare simulation and safety-report parameters."""
    reg.category("sim", "Simulation settings")
    reg.number("sim.time_step", 1.0, "ms", 0.1, 5.0, "Time step",
               "Step of the physics and control loop. 1 ms is the tested default; "
               "larger steps are faster but less accurate.")
    reg.number("sim.log_rate", 100.0, "Hz", 5.0, 1000.0, "Recording rate",
               "How many samples per second are stored in the results. The safety "
               "monitor checks at this rate too.")
    reg.integer("sim.random_seed", 1, 0, 1000000, "Random seed",
                "Starting number for sensor noise and road bumps. The same seed gives "
                "exactly the same run.")
    reg.number("sim.route_sample_spacing", 0.25, "m", 0.05, 2.0, "Route sample spacing",
               "Distance between the points the route is broken into.")
    reg.number("sim.max_duration", 1800.0, "s", 1.0, 36000.0, "Longest run",
               "A simulation always stops after this much simulated time.")

    reg.number("sim.stopped_speed", 0.05, "m/s", 0.001, 1.0, "Standstill speed",
               "Below this speed the vehicle counts as stopped.")

    reg.category("safety", "Safety report limits")
    reg.number("safety.wheel_lift_min_height", 5.0, "mm", 0.0, 100.0, "Wheel lift: least gap",
               "A wheel counts as lifted when it is at least this far off the ground.")
    reg.number("safety.wheel_lift_min_time", 0.05, "s", 0.0, 2.0, "Wheel lift: least time",
               "Shorter hops (bumps) are not reported as wheel lift.")
    reg.number("safety.slip_ratio_limit", 25.0, "%", 5.0, 100.0, "Wheel spin limit",
               "Drive slip above this is reported as wheel spin.")
    reg.number("safety.lock_slip_limit", 70.0, "%", 20.0, 100.0, "Wheel lock limit",
               "Brake slip above this is reported as a locked wheel.")
    reg.number("safety.slip_angle_limit", 15.0, "deg", 3.0, 60.0, "Sideways slide limit",
               "A slip angle above this is reported as sliding sideways.")
    reg.number("safety.min_speed_for_slip", 1.5, "m/s", 0.1, 10.0, "Least speed for slip checks",
               "Below this speed slip values are not meaningful and are not reported.")
    reg.number("safety.rollover_angle", 60.0, "deg", 20.0, 90.0, "Rolled-over angle",
               "Roll or pitch angle at which the run stops as 'rolled over'.")
