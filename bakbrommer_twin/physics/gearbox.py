"""Clutch and gearbox between the petrol engine and the rear wheel.

Gearbox: ``manual`` (fixed gear ratios, drive interrupted while shifting) or
``cvt`` (ratio follows a target engine speed with a lag). The total ratio is
R = primary × gear × final, so that engine speed = R × wheel speed when the
clutch is locked.

Centrifugal clutch: the torque it can carry grows with the square of the
engine speed between the engagement and the full-grip speed (centrifugal
force ∝ ω²):  capacity = T_max·clamp((ω² − ω_e²)/(ω_l² − ω_e²), 0, 1).

Stick/slip solution (see docs/PHYSICS.md, "Friction as a constraint")
---------------------------------------------------------------------
Clutch torque T_c and the rear wheel friction torque T_f (brake + rolling
resistance + drag) are dry-friction torques: they take exactly the value that
stops the relative motion, but never more than their capacity. Over one step

    ω_e⁺ = ω_e + dt·(T_e − T_c)/J_e
    ω_w⁺ = ω_w + dt·(T_ext + R·e·T_c − T_f)/I_w

Clutch slip after the step is ω_e⁺ − R·ω_w⁺; setting it to zero gives the
"locking" torque, which is then limited to ±capacity. The same is done for
the wheel friction (ω_w⁺ = 0). The two are coupled, so they are solved in
turn a few times (Gauss–Seidel). This is unconditionally stable and gives a
true lock-up. ``e`` is the driveline efficiency (η when the engine drives,
1/η when the wheel drives the engine).
"""

from __future__ import annotations

from bakbrommer_twin.params.paramset import ParamSet

_SOLVER_PASSES = 3  # Gauss–Seidel passes over the two friction constraints
NEUTRAL = 0


class Driveline:
    """Gearbox + clutch state and the coupled engine/rear-wheel speed update."""

    __slots__ = ("capacity", "clutch_loss", "clutch_max", "clutch_torque", "cvt_high",
                 "cvt_low", "cvt_ratio", "cvt_response", "cvt_speed_full", "cvt_speed_low",
                 "drag_torque", "efficiency", "engage_sq", "final", "friction_torque",
                 "gear", "gear_loss", "gears", "is_cvt", "lockup_sq", "pending_gear",
                 "primary", "ratio", "shift_remaining", "shift_time", "wheel_torque")

    def __init__(self, params: ParamSet) -> None:
        self.is_cvt = params.choice("gearbox.type") == "cvt"
        self.primary = params.num("gearbox.primary_ratio")
        self.gears = params.curve("gearbox.gear_ratios")
        self.final = params.num("gearbox.final_drive_ratio")
        self.efficiency = params.num("gearbox.efficiency")
        self.shift_time = params.num("gearbox.shift_time")
        self.drag_torque = params.num("gearbox.drag_torque")
        self.cvt_low = params.num("gearbox.cvt_ratio_low")
        self.cvt_high = params.num("gearbox.cvt_ratio_high")
        self.cvt_speed_low = params.num("gearbox.cvt_speed_low_throttle")
        self.cvt_speed_full = params.num("gearbox.cvt_speed_full_throttle")
        self.cvt_response = params.num("gearbox.cvt_response_time")
        engage = params.num("clutch.engage_speed")
        lockup = params.num("clutch.lockup_speed")
        if lockup <= engage:
            raise ValueError("clutch.lockup_speed must be above clutch.engage_speed")
        if self.cvt_low <= self.cvt_high:
            raise ValueError("gearbox.cvt_ratio_low must be above gearbox.cvt_ratio_high")
        self.engage_sq = engage * engage
        self.lockup_sq = lockup * lockup
        self.clutch_max = params.num("clutch.max_torque")
        self.gear = 1  # 0 = neutral, 1…N
        self.pending_gear = 1
        self.shift_remaining = 0.0  # s left of the current gear change
        self.cvt_ratio = self.cvt_low
        self.ratio = self.total_ratio(1)
        self.capacity = 0.0  # clutch torque capacity this step, Nm
        self.clutch_torque = 0.0  # torque through the clutch at the crank, Nm
        self.wheel_torque = 0.0  # resulting torque on the rear wheel, Nm
        self.friction_torque = 0.0  # wheel friction torque actually applied, Nm
        self.clutch_loss = 0.0  # W dissipated by clutch slip
        self.gear_loss = 0.0  # W dissipated in gears and chain

    @property
    def gear_count(self) -> int:
        """Number of selectable gears (1 for a CVT)."""
        return 1 if self.is_cvt else len(self.gears)

    @property
    def shifting(self) -> bool:
        """True while a gear change interrupts the drive."""
        return self.shift_remaining > 0.0

    def total_ratio(self, gear: int) -> float:
        """Engine speed / wheel speed in ``gear`` (CVT: at the present belt ratio)."""
        middle = self.cvt_ratio if self.is_cvt else self.gears[gear - 1]
        return self.primary * middle * self.final

    def select_gear(self, gear: int) -> None:
        """Engage a gear at once (for setting up the start of a run)."""
        self.gear = self.pending_gear = max(NEUTRAL, min(gear, self.gear_count))
        self.shift_remaining = 0.0
        if self.gear != NEUTRAL:
            self.ratio = self.total_ratio(self.gear)

    def update(self, dt: float, gear_request: int, engine_speed: float, wheel_speed: float,
               throttle: float) -> None:
        """Handle gear changes / CVT ratio and compute the clutch capacity."""
        if self.is_cvt:
            # The variator seeks the ratio that puts the engine at its target speed.
            target_speed = self.cvt_speed_low + throttle * (
                self.cvt_speed_full - self.cvt_speed_low)
            input_speed = abs(wheel_speed) * self.primary * self.final
            wanted = self.cvt_low if input_speed * self.cvt_low < target_speed else (
                target_speed / input_speed)
            wanted = max(self.cvt_high, min(self.cvt_low, wanted))
            self.cvt_ratio += (wanted - self.cvt_ratio) * min(1.0, dt / self.cvt_response)
            self.ratio = self.total_ratio(1)
        else:
            requested = max(NEUTRAL, min(gear_request, self.gear_count))
            if self.shift_remaining > 0.0:
                self.shift_remaining -= dt
                if self.shift_remaining <= 0.0:
                    self.gear = self.pending_gear
                    if self.gear != NEUTRAL:
                        self.ratio = self.total_ratio(self.gear)
            elif requested != self.gear:
                self.pending_gear = requested
                self.shift_remaining = self.shift_time
        if self.shift_remaining > 0.0 or self.gear == NEUTRAL:
            self.capacity = 0.0
        else:
            grip = (engine_speed * engine_speed - self.engage_sq) / (
                self.lockup_sq - self.engage_sq)
            grip = 0.0 if grip < 0.0 else (1.0 if grip > 1.0 else grip)
            self.capacity = self.clutch_max * grip

    def solve(self, dt: float, engine_speed: float, engine_torque: float,
              engine_inertia: float, wheel_speed: float, wheel_inertia: float,
              external_torque: float, friction_capacity: float) -> tuple[float, float]:
        """Advance engine and rear wheel speed by ``dt``; return the new speeds.

        ``external_torque`` is everything on the wheel except clutch and
        friction (the tyre reaction). ``friction_capacity`` ≥ 0 is the most the
        brake + rolling resistance + drag can hold.
        """
        ratio = self.ratio
        capacity = self.capacity
        gain_engine = dt / engine_inertia
        gain_wheel = dt / wheel_inertia
        engine_free = engine_speed + gain_engine * engine_torque
        clutch = 0.0
        friction = 0.0
        wheel_drive = 0.0
        for _ in range(_SOLVER_PASSES):
            if capacity > 0.0:
                wheel_partial = wheel_speed + gain_wheel * (external_torque - friction)
                slip_free = engine_free - ratio * wheel_partial
                factor = self.efficiency if slip_free >= 0.0 else 1.0 / self.efficiency
                clutch = slip_free / (gain_engine + ratio * ratio * factor * gain_wheel)
                clutch = capacity if clutch > capacity else (
                    -capacity if clutch < -capacity else clutch)
                wheel_drive = ratio * factor * clutch
            wheel_free = wheel_speed + gain_wheel * (external_torque + wheel_drive)
            friction = wheel_free / gain_wheel
            friction = friction_capacity if friction > friction_capacity else (
                -friction_capacity if friction < -friction_capacity else friction)
        new_engine = engine_free - gain_engine * clutch
        if new_engine < 0.0:
            new_engine = 0.0
        if -friction_capacity < friction < friction_capacity:
            new_wheel = 0.0  # friction not used up: the wheel stands exactly still
        else:
            new_wheel = wheel_speed + gain_wheel * (external_torque + wheel_drive - friction)
        self.clutch_torque = clutch
        self.wheel_torque = wheel_drive
        self.friction_torque = friction
        self.clutch_loss = clutch * (new_engine - ratio * new_wheel)
        self.gear_loss = (ratio * clutch - wheel_drive) * new_wheel
        return new_engine, new_wheel
