"""Parameters: petrol engine, clutch and gearbox (rear wheel drive)."""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Status

EST = Status.ESTIMATED
GEARBOX_TYPES: tuple[str, ...] = ("manual", "cvt")


def register(reg: Registry) -> None:
    """Declare engine, clutch and gearbox parameters."""
    _engine(reg)
    _clutch(reg)
    _gearbox(reg)


def _engine(reg: Registry) -> None:
    reg.category("engine", "Petrol engine")
    reg.curve("engine.torque_curve_speed",
              [1500, 2500, 3500, 4500, 5500, 6500, 7500, 8500, 9000], "rpm", 500, 14000,
              "Torque curve: engine speed",
              "Engine speed points of the full-throttle torque curve (rising).", EST)
    reg.curve("engine.torque_curve_torque", [4.5, 5.6, 6.3, 6.8, 7.0, 6.8, 6.4, 5.4, 4.5],
              "Nm", 0, 60, "Torque curve: torque",
              "Crankshaft torque at full throttle at each speed point (Lifan 110 cc).", EST)
    reg.number("engine.friction_torque", 0.8, "Nm", 0.0, 10.0, "Friction torque at standstill",
               "Torque lost to friction and pumping, extrapolated to zero speed.", EST)
    reg.number("engine.friction_torque_speed", 0.0010, "Nm·s/rad", 0.0, 0.02,
               "Friction torque growth",
               "Extra friction torque per rad/s of engine speed. Friction is what "
               "brakes the vehicle when the throttle is closed.", EST)
    reg.number("engine.inertia", 0.012, "kg·m²", 0.001, 0.2, "Engine inertia",
               "Rotational inertia of crankshaft, flywheel and clutch.", EST)
    reg.number("engine.idle_speed", 1500.0, "rpm", 600.0, 3000.0, "Idle speed",
               "Engine speed with closed throttle and open clutch.", EST)
    reg.number("engine.idle_gain", 0.05, "s/rad", 0.0005, 0.5, "Idle control gain",
               "How strongly the idle system opens the throttle per rad/s below idle.")
    reg.number("engine.rev_limit", 9000.0, "rpm", 3000.0, 14000.0, "Rev limiter",
               "Engine speed at which the ignition cuts out.", EST)
    reg.number("engine.min_firing_speed", 400.0, "rpm", 100.0, 1500.0, "Minimum running speed",
               "Below this speed the engine cannot run by itself (stalls).", EST)
    reg.number("engine.starter_torque", 6.0, "Nm", 0.5, 40.0, "Starter torque",
               "Torque of the electric starter at the crankshaft.", EST)
    reg.number("engine.starter_cutoff_speed", 800.0, "rpm", 200.0, 2500.0, "Starter cut-off",
               "Engine speed at which the starter stops helping.", EST)
    reg.number("engine.throttle_response_time", 60.0, "ms", 5.0, 1000.0,
               "Throttle response time",
               "Time constant with which engine torque follows the throttle.", EST)
    reg.flag("engine.throttle_by_wire", False, "Throttle by wire",
             "On: the STM32 controller sets the petrol throttle (servo). "
             "Off: the rider's twist grip pulls the carburettor cable directly.")
    reg.number("engine.indicated_efficiency", 28.0, "%", 10.0, 45.0, "Combustion efficiency",
               "Share of the fuel energy turned into work on the piston (before "
               "friction). Sets the fuel consumption.", EST)
    reg.number("engine.fuel_heating_value", 43.0, "MJ/kg", 20.0, 50.0, "Fuel heating value",
               "Energy content of petrol per kilogram.", Status.MEASURED)
    reg.number("engine.fuel_density", 0.745, "kg/L", 0.6, 0.9, "Fuel density",
               "Mass of one litre of petrol.", Status.MEASURED)
    reg.number("engine.fuel_tank_volume", 4.0, "L", 0.5, 30.0, "Fuel tank volume",
               "Size of the petrol tank (used for the range estimate).", EST)


def _clutch(reg: Registry) -> None:
    reg.category("clutch", "Clutch")
    reg.number("clutch.engage_speed", 2300.0, "rpm", 800.0, 6000.0, "Engagement speed",
               "Engine speed at which the centrifugal clutch starts to grip.", EST)
    reg.number("clutch.lockup_speed", 3800.0, "rpm", 1000.0, 9000.0, "Full-grip speed",
               "Engine speed at which the clutch reaches its full torque capacity.", EST)
    reg.number("clutch.max_torque", 16.0, "Nm", 2.0, 100.0, "Torque capacity",
               "Largest crankshaft torque the fully engaged clutch can carry.", EST)


def _gearbox(reg: Registry) -> None:
    reg.category("gearbox", "Gearbox")
    reg.choice("gearbox.type", "manual", GEARBOX_TYPES, "Gearbox type",
               "manual: foot-shifted gears with centrifugal clutch. "
               "cvt: stepless belt drive with centrifugal clutch.")
    reg.number("gearbox.primary_ratio", 4.059, "-", 1.0, 10.0, "Primary reduction",
               "Reduction between crankshaft and gearbox input.", EST)
    reg.curve("gearbox.gear_ratios", [2.833, 1.706, 1.238, 0.958], "-", 0.3, 6.0,
              "Gear ratios", "Ratio of each gear, first gear first (manual gearbox).", EST)
    reg.number("gearbox.final_drive_ratio", 2.57, "-", 1.0, 8.0, "Final drive ratio",
               "Rear sprocket teeth divided by front sprocket teeth.", EST)
    reg.number("gearbox.efficiency", 92.0, "%", 60.0, 100.0, "Driveline efficiency",
               "Share of the engine torque that reaches the wheel (gears and chain).", EST)
    reg.number("gearbox.shift_time", 0.35, "s", 0.05, 2.0, "Shift time",
               "Time without drive during a gear change.", EST)
    reg.number("gearbox.drag_torque", 0.6, "Nm", 0.0, 10.0, "Driveline drag at the wheel",
               "Friction torque of chain, bearings and gearbox felt at the rear wheel.", EST)
    reg.number("gearbox.cvt_ratio_low", 2.6, "-", 0.8, 6.0, "CVT lowest gear ratio",
               "CVT only: belt ratio when pulling away.", EST)
    reg.number("gearbox.cvt_ratio_high", 0.85, "-", 0.3, 3.0, "CVT highest gear ratio",
               "CVT only: belt ratio at top speed.", EST)
    reg.number("gearbox.cvt_speed_low_throttle", 3500.0, "rpm", 1500.0, 9000.0,
               "CVT engine speed, light throttle",
               "CVT only: engine speed the belt drive holds at closed throttle.", EST)
    reg.number("gearbox.cvt_speed_full_throttle", 7000.0, "rpm", 2500.0, 12000.0,
               "CVT engine speed, full throttle",
               "CVT only: engine speed the belt drive holds at full throttle.", EST)
    reg.number("gearbox.cvt_response_time", 0.4, "s", 0.05, 5.0, "CVT response time",
               "CVT only: time constant of ratio changes.", EST)
