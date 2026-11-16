"""Steady-state performance estimates from the subsystem models.

These are quick hand-calculation style figures (no simulation) for the
"calculated values" page: gear speeds, power, top speed estimate. They reuse
the same engine, motor and battery classes as the simulator, so they always
agree with it.
"""

from __future__ import annotations

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics import mass
from bakbrommer_twin.physics.aero import drag_area
from bakbrommer_twin.physics.battery import Battery
from bakbrommer_twin.physics.engine import Engine
from bakbrommer_twin.physics.gearbox import Driveline
from bakbrommer_twin.physics.motors import ElectricDrive
from bakbrommer_twin.physics.surfaces import load_surfaces

_SCAN_STEP = 0.1  # m/s, resolution of the top speed search
_SCAN_LIMIT = 70.0  # m/s, upper end of the top speed search
_MID_CHARGE = 0.5  # state of charge used for "nominal" battery voltage


def nominal_battery_voltage(params: ParamSet) -> float:
    """Rest voltage of the pack at 50 % state of charge, V."""
    battery = Battery(params)
    battery.soc = _MID_CHARGE
    return battery.open_circuit_voltage()


def engine_peak_power(params: ParamSet) -> tuple[float, float]:
    """(peak crankshaft power W, engine speed rad/s at that point)."""
    speeds = params.curve("engine.torque_curve_speed")
    torques = params.curve("engine.torque_curve_torque")
    power, speed = max((t * w, w) for w, t in zip(speeds, torques, strict=True))
    return power, speed


def gear_speeds(params: ParamSet) -> list[float]:
    """Road speed at the rev limiter in each gear, m/s (one entry for a CVT)."""
    driveline = Driveline(params)
    radius = params.num("wheels.rear_radius")
    limit = params.num("engine.rev_limit")
    if driveline.is_cvt:
        driveline.cvt_ratio = driveline.cvt_high
    return [limit / driveline.total_ratio(gear) * radius
            for gear in range(1, driveline.gear_count + 1)]


def engine_wheel_power(params: ParamSet, speed: float) -> float:
    """Most power the petrol drive can put on the rear wheel at road speed, W."""
    engine, driveline = Engine(params), Driveline(params)
    wheel_speed = speed / params.num("wheels.rear_radius")
    engage = params.num("clutch.lockup_speed")
    best = 0.0
    if driveline.is_cvt:
        # A CVT can hold the engine at its power peak between its ratio limits.
        candidates = [params.num("gearbox.cvt_ratio_low"), params.num("gearbox.cvt_ratio_high")]
        peak_speed = engine_peak_power(params)[1]
        ideal = peak_speed / (wheel_speed * driveline.primary * driveline.final) if (
            wheel_speed > 0.0) else candidates[0]
        candidates.append(min(candidates[0], max(candidates[1], ideal)))
        ratios = [driveline.primary * c * driveline.final for c in candidates]
    else:
        ratios = [driveline.total_ratio(g) for g in range(1, driveline.gear_count + 1)]
    for ratio in ratios:
        engine_speed = wheel_speed * ratio
        if engine_speed < engage:
            continue  # clutch not fully engaged at this speed in this gear
        power = engine.full_throttle_torque(engine_speed) * engine_speed
        best = max(best, power * driveline.efficiency)
    return best


def electric_wheel_power(params: ParamSet, speed: float) -> float:
    """Most power both hub motors together can put on the road at road speed, W."""
    drive = ElectricDrive(params)
    omega = speed / params.num("wheels.front_radius")
    voltage = nominal_battery_voltage(params)
    torque = drive.max_drive_torque(omega, voltage) - drive.drag_static - drive.drag_speed * omega
    return max(0.0, 2.0 * torque * omega)


def resistance_power(params: ParamSet, speed: float) -> float:
    """Power needed to hold ``speed`` on a level dry road in still air, W."""
    surface = load_surfaces(params)[next(iter(load_surfaces(params)))]
    props = mass.mass_properties(params)
    rolling = surface.rolling_resistance * (
        1.0 + params.num("tyre.rolling_resistance_speed_factor") * speed * speed)
    # P = (½·ρ·CdA·v² + c_rr·m·g)·v
    drag = 0.5 * params.num("environment.air_density") * drag_area(params) * speed * speed
    return (drag + rolling * props.mass * mass.GRAVITY) * speed


def top_speed_estimate(params: ParamSet) -> float:
    """Highest speed at which available power still covers the resistance, m/s."""
    best = 0.0
    steps = round(_SCAN_LIMIT / _SCAN_STEP)
    for i in range(1, steps + 1):
        speed = i * _SCAN_STEP
        available = engine_wheel_power(params, speed) + electric_wheel_power(params, speed)
        if available >= resistance_power(params, speed):
            best = speed
    return best


def electric_power_limit(params: ParamSet) -> float:
    """Battery power the motors may draw (controller and BMS limits), W."""
    current = min(2.0 * params.num("motor.line_current_limit"),
                  params.num("battery.bms_discharge_limit"))
    return current * nominal_battery_voltage(params)
