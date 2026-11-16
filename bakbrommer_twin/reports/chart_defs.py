"""The standard charts: which channels are drawn together.

To add a chart: append a ``ChartDef`` to ``CHARTS``. All channels of one chart
must have the same unit (a test checks this) — there is never a second
y-axis. The title is translated through ``chart.<key>``.
"""

from __future__ import annotations

from dataclasses import dataclass

from bakbrommer_twin.sim.result import RunResult


@dataclass(frozen=True)
class ChartDef:
    """One chart: a key (for its translated title) and the channels it shows."""

    key: str
    channels: tuple[str, ...]


CHARTS: tuple[ChartDef, ...] = (
    ChartDef("speed", ("speed", "target_speed", "ctl_speed_estimate")),
    ChartDef("pedals", ("throttle", "brake_front", "brake_rear")),
    ChartDef("steering", ("steer",)),
    ChartDef("acceleration", ("accel_x", "accel_y")),
    ChartDef("wheel_loads", ("load_fl", "load_fr", "load_r")),
    ChartDef("wheel_lift", ("gap_fl", "gap_fr", "gap_r")),
    ChartDef("roll_pitch", ("roll", "pitch")),
    ChartDef("rollover_margin", ("rollover_margin",)),
    ChartDef("slip_ratio", ("slip_ratio_fl", "slip_ratio_fr", "slip_ratio_r")),
    ChartDef("slip_angle", ("slip_angle_fl", "slip_angle_fr", "slip_angle_r")),
    ChartDef("wheel_torque", ("torque_fl", "torque_fr", "torque_r")),
    ChartDef("wheel_speed", ("wheel_speed_fl", "wheel_speed_fr", "wheel_speed_r")),
    ChartDef("battery_current", ("battery_current", "motor_current_l", "motor_current_r")),
    ChartDef("battery_voltage", ("battery_voltage",)),
    ChartDef("battery_soc", ("battery_soc",)),
    ChartDef("temperatures", ("motor_temp_l", "motor_temp_r", "battery_temp")),
    ChartDef("engine_speed", ("engine_speed",)),
    ChartDef("gear", ("gear",)),
    ChartDef("interventions", ("ctl_traction_left", "ctl_traction_right", "ctl_power_limit",
                               "ctl_stability_limit")),
    ChartDef("torque_commands", ("ctl_torque_left", "ctl_torque_right")),
    ChartDef("ride_mode", ("ctl_mode",)),
    ChartDef("route_offset", ("route_offset",)),
)
CHARTS_BY_KEY: dict[str, ChartDef] = {chart.key: chart for chart in CHARTS}
DEFAULT_CHARTS: tuple[str, ...] = ("speed", "pedals", "wheel_loads", "wheel_lift",
                                   "battery_current")
REPORT_CHARTS: tuple[str, ...] = ("speed", "pedals", "acceleration", "wheel_loads",
                                  "wheel_lift", "rollover_margin", "slip_ratio",
                                  "battery_current", "temperatures", "interventions")


def charts_for_channels(result: RunResult, channels: list[str]) -> list[ChartDef]:
    """Group freely chosen channels into charts, one chart per unit."""
    by_unit: dict[str, list[str]] = {}
    for name in channels:
        by_unit.setdefault(result.info(name).unit, []).append(name)
    return [ChartDef(f"custom_{index}", tuple(names))
            for index, names in enumerate(by_unit.values())]
