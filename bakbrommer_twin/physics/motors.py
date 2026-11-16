"""Electric hub motor with its Fardriver controller (one instance per front wheel).

Model (surface-mounted permanent-magnet motor under field-oriented control)
---------------------------------------------------------------------------
* Torque is proportional to the torque-producing phase current:
  T = K_t·I_q  (I_q = peak value of the phase current sine).
* Back-EMF: the phase voltage amplitude induced at wheel speed ω is
  E = K_e·ω with K_e = K_t/1.5 (power balance of a three-phase machine:
  T·ω = 1.5·E·I_q).
* The controller can make a phase voltage of at most m·V_bus (m ≤ 1/√3).
  Voltage limit on current: I_q ≤ (m·V_bus·f_w − K_e·|ω|)/R, where f_w ≥ 1
  stretches the speed range by field weakening (simplified: the extra
  d-axis current and its losses are not modelled).
* Losses: copper P_cu = 1.5·R·I_q² (R rises with copper temperature),
  drag torque d0 + d1·|ω| (bearings, cogging, iron losses), controller
  efficiency η_c and a standby power.
* Battery-side power while driving: P_bus = (T·ω + P_cu)/η_c + P_standby;
  while regenerating: P_bus = (T·ω + P_cu)·η_c + P_standby (negative).
* One-node thermal model: C·dT/dt = P_cu + P_drag − G(v)·(T − T_air),
  G(v) = G0·(1 + k·v) with v the rim speed. Above the derating start
  temperature the torque limit falls linearly to zero at the maximum.

Units: torque Nm, speed rad/s, voltage V, current A, power W, temperature °C.
"""

from __future__ import annotations

import math

from bakbrommer_twin.params.paramset import ParamSet

COPPER_TEMP_COEFFICIENT = 0.00393  # 1/K, resistance rise of copper (material constant)
REFERENCE_TEMPERATURE = 20.0  # °C at which the phase resistance is specified


class ElectricDrive:
    """One hub motor + controller. Call :meth:`step` each time step."""

    __slots__ = (
        "bus_current", "controller_efficiency", "cooling_factor", "copper_loss",
        "derate", "derate_start", "drag_power", "drag_speed", "drag_static", "drag_torque",
        "field_weakening", "ke", "kt", "line_limit", "max_temperature", "modulation",
        "peak_current", "regen_current", "regen_fade_end", "regen_fade_start",
        "regen_line_limit", "resistance_20", "response_time", "standby_power",
        "temperature", "thermal_capacity", "thermal_conductance", "torque",
        "torque_filtered", "wheel_radius",
    )

    def __init__(self, params: ParamSet) -> None:
        self.kt = params.num("motor.torque_constant")
        self.ke = self.kt / 1.5  # V·s/rad, phase back-EMF amplitude per rad/s
        self.resistance_20 = params.num("motor.phase_resistance")
        self.peak_current = params.num("motor.peak_phase_current")
        self.line_limit = params.num("motor.line_current_limit")
        self.regen_current = params.num("motor.regen_phase_current")
        self.regen_line_limit = params.num("motor.regen_line_current_limit")
        self.regen_fade_start = params.num("motor.regen_fade_start_speed")
        self.regen_fade_end = params.num("motor.regen_fade_end_speed")
        self.modulation = params.num("motor.modulation_limit")
        self.field_weakening = params.num("motor.field_weakening_ratio")
        self.drag_static = params.num("motor.drag_torque_static")
        self.drag_speed = params.num("motor.drag_torque_speed")
        self.controller_efficiency = params.num("motor.controller_efficiency")
        self.standby_power = params.num("motor.standby_power")
        self.response_time = params.num("motor.torque_response_time")
        self.thermal_capacity = params.num("motor.thermal_capacity")
        self.thermal_conductance = params.num("motor.thermal_conductance")
        self.cooling_factor = params.num("motor.cooling_speed_factor")
        self.derate_start = params.num("motor.derate_start_temperature")
        self.max_temperature = params.num("motor.max_temperature")
        self.wheel_radius = params.num("wheels.front_radius")
        if self.regen_fade_end <= self.regen_fade_start:
            raise ValueError("motor.regen_fade_end_speed must be above regen_fade_start_speed")
        if self.max_temperature <= self.derate_start:
            raise ValueError("motor.max_temperature must be above derate_start_temperature")
        self.temperature = params.num("environment.air_temperature")
        self.torque_filtered = 0.0  # command after the response lag, Nm
        self.torque = 0.0  # electromagnetic torque on the wheel, Nm
        self.drag_torque = 0.0  # friction-like drag magnitude, Nm (≥ 0)
        self.bus_current = 0.0  # battery-side current, A (+ = drawing)
        self.copper_loss = 0.0  # W
        self.drag_power = 0.0  # W
        self.derate = 1.0  # thermal torque factor 0…1

    def resistance(self) -> float:
        """Phase resistance at the present temperature, Ω."""
        return self.resistance_20 * (
            1.0 + COPPER_TEMP_COEFFICIENT * (self.temperature - REFERENCE_TEMPERATURE))

    def max_drive_torque(self, omega: float, bus_voltage: float) -> float:
        """Largest driving torque available at wheel speed ``omega``, Nm."""
        speed = abs(omega)
        resistance = self.resistance()
        limit = self.kt * self.peak_current * self.derate  # phase current limit
        # Voltage limit: I_q ≤ (m·V·f_w − K_e·ω)/R.
        headroom = self.modulation * bus_voltage * self.field_weakening - self.ke * speed
        limit = min(limit, self.kt * max(0.0, headroom) / resistance)
        # Line current limit: (K_t·I_q·ω + 1.5·R·I_q²)/η_c + P_sb ≤ V·I_line.
        # Solve 1.5·R·I_q² + K_t·ω·I_q − P = 0 for the positive root.
        available = self.controller_efficiency * (
            bus_voltage * self.line_limit - self.standby_power)
        if available <= 0.0:
            return 0.0
        back = self.kt * speed
        iq = (-back + math.sqrt(back * back + 6.0 * resistance * available)) / (3.0 * resistance)
        return min(limit, self.kt * iq)

    def max_regen_torque(self, omega: float, bus_voltage: float) -> float:
        """Largest braking torque magnitude available at wheel speed ``omega``, Nm."""
        rim_speed = abs(omega) * self.wheel_radius
        fade = (rim_speed - self.regen_fade_start) / (self.regen_fade_end - self.regen_fade_start)
        if fade <= 0.0:
            return 0.0
        fade = min(fade, 1.0)
        limit = self.kt * self.regen_current * self.derate * fade
        # Charging current limit: (K_t·I_q·ω − 1.5·R·I_q²)·η_c ≤ V·I_regen.
        # 1.5·R·I_q² − K_t·ω·I_q + P/η_c ≥ 0 holds below the smaller root.
        resistance = self.resistance()
        back = self.kt * abs(omega)
        power = bus_voltage * self.regen_line_limit / self.controller_efficiency
        discriminant = back * back - 6.0 * resistance * power
        if discriminant > 0.0:
            limit = min(limit, self.kt * (back - math.sqrt(discriminant)) / (3.0 * resistance))
        return limit

    def step(self, dt: float, torque_command: float, omega: float, bus_voltage: float,
             bus_on: bool, air_temperature: float) -> None:
        """Advance one step. ``torque_command`` > 0 drives forwards, < 0 brakes (regen)."""
        # First-order lag of the current loop: dT/dt = (T_cmd − T)/τ (exact discretisation
        # is not needed; τ ≫ dt).
        self.torque_filtered += (torque_command - self.torque_filtered) * min(
            1.0, dt / self.response_time)
        derate = (self.max_temperature - self.temperature) / (
            self.max_temperature - self.derate_start)
        self.derate = 0.0 if derate < 0.0 else (1.0 if derate > 1.0 else derate)

        wanted = self.torque_filtered
        if not bus_on:
            torque = 0.0
        elif wanted >= 0.0:
            torque = min(wanted, self.max_drive_torque(omega, bus_voltage))
        elif omega > 0.0:
            torque = -min(-wanted, self.max_regen_torque(omega, bus_voltage))
        else:
            torque = 0.0  # no reverse drive: braking torque needs a forward-turning wheel
        self.torque = torque

        speed = abs(omega)
        iq = torque / self.kt
        self.copper_loss = 1.5 * self.resistance() * iq * iq
        self.drag_torque = self.drag_static + self.drag_speed * speed
        self.drag_power = self.drag_torque * speed
        electrical = torque * omega + self.copper_loss  # W at the motor terminals
        if not bus_on:
            bus_power = 0.0
        elif electrical >= 0.0:
            bus_power = electrical / self.controller_efficiency + self.standby_power
        else:
            bus_power = electrical * self.controller_efficiency + self.standby_power
        self.bus_current = bus_power / bus_voltage if bus_voltage > 0.0 else 0.0

        # Thermal node: C·dT/dt = heat − G(v)·(T − T_air).
        conductance = self.thermal_conductance * (
            1.0 + self.cooling_factor * speed * self.wheel_radius)
        heat = self.copper_loss + self.drag_power
        self.temperature += dt * (
            heat - conductance * (self.temperature - air_temperature)) / self.thermal_capacity

    def efficiency(self, torque: float, omega: float) -> float:
        """Battery-to-wheel efficiency at a driving operating point (for the map), 0…1."""
        if torque <= 0.0 or omega <= 0.0:
            return 0.0
        iq = torque / self.kt
        shaft = (torque - self.drag_static - self.drag_speed * omega) * omega
        bus = (torque * omega + 1.5 * self.resistance() * iq * iq) / self.controller_efficiency
        bus += self.standby_power
        return max(0.0, shaft / bus)
