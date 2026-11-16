"""Petrol engine (crankshaft torque and fuel use).

Model
-----
* Full-throttle torque curve T_wot(ω) from the parameters (net torque at the
  crankshaft, as a dynamometer would measure it).
* Friction/pumping torque T_f(ω) = f0 + f1·ω.
* Part throttle (mean-value engine model, e.g. Guzzella & Onder,
  "Introduction to Modeling and Control of IC Engine Systems"):
      T = load·(T_wot + T_f) − T_f
  so load = 1 gives the torque curve and load = 0 gives engine braking −T_f.
  ``load`` follows the throttle with a first-order lag.
* Idle system: opens the throttle in proportion to the speed below idle.
* Rev limiter: load = 0 above the limit. The engine only fires when the
  ignition is on and it turns faster than the minimum running speed.
* Fuel (Willans line, Guzzella & Sciarretta, "Vehicle Propulsion Systems"):
      fuel power = indicated power / η_i,  indicated power = load·(T_wot + T_f)·ω
  with at least the idle fuel flow while running.

The engine speed itself is integrated by the driveline (clutch) solver.
Units: torque Nm, speed rad/s, fuel kg/s.
"""

from __future__ import annotations

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.lookup import Curve


class Engine:
    """The petrol engine. Call :meth:`update` each step, then let the driveline move it."""

    __slots__ = ("efficiency", "friction0", "friction1", "fuel_density", "fuel_rate",
                 "fuel_used", "heating_value", "idle_fuel_rate", "idle_gain", "idle_speed",
                 "inertia", "load", "min_firing_speed", "response_time", "rev_limit",
                 "running", "speed", "starter_cutoff", "starter_torque", "torque",
                 "torque_curve")

    def __init__(self, params: ParamSet) -> None:
        self.torque_curve = Curve(params.curve("engine.torque_curve_speed"),
                                  params.curve("engine.torque_curve_torque"),
                                  "engine torque curve")
        self.friction0 = params.num("engine.friction_torque")
        self.friction1 = params.num("engine.friction_torque_speed")
        self.inertia = params.num("engine.inertia")
        self.idle_speed = params.num("engine.idle_speed")
        self.idle_gain = params.num("engine.idle_gain")
        self.rev_limit = params.num("engine.rev_limit")
        self.min_firing_speed = params.num("engine.min_firing_speed")
        self.starter_torque = params.num("engine.starter_torque")
        self.starter_cutoff = params.num("engine.starter_cutoff_speed")
        self.response_time = params.num("engine.throttle_response_time")
        self.efficiency = params.num("engine.indicated_efficiency")
        self.heating_value = params.num("engine.fuel_heating_value")  # J/kg
        self.fuel_density = params.num("engine.fuel_density")  # kg/m³
        # Fuel flow that just overcomes friction at idle speed, kg/s.
        self.idle_fuel_rate = (self.friction(self.idle_speed) * self.idle_speed
                               / (self.efficiency * self.heating_value))
        self.speed = 0.0  # crankshaft speed, rad/s
        self.load = 0.0  # 0…1, throttle after the response lag
        self.torque = 0.0  # net crankshaft torque before the clutch, Nm
        self.running = False
        self.fuel_rate = 0.0  # kg/s
        self.fuel_used = 0.0  # kg

    def friction(self, speed: float) -> float:
        """Friction and pumping torque at ``speed``, Nm."""
        return self.friction0 + self.friction1 * speed

    def full_throttle_torque(self, speed: float) -> float:
        """Net full-throttle torque at ``speed`` (zero above the rev limit), Nm."""
        return self.torque_curve(speed) if speed <= self.rev_limit else 0.0

    def start_running(self) -> None:
        """Put the engine at idle (used for scenarios that start with a warm engine)."""
        self.speed = self.idle_speed
        self.running = True
        friction = self.friction(self.speed)
        self.load = friction / (self.torque_curve(self.speed) + friction)

    def update(self, dt: float, throttle: float, ignition: bool, starter: bool) -> None:
        """Compute torque and fuel flow for this step."""
        speed = self.speed
        self.running = ignition and speed >= self.min_firing_speed
        friction = self.friction(speed) if speed > 0.0 else 0.0
        indicated_max = self.torque_curve(speed) + friction
        if self.running:
            demand = throttle
            idle_demand = self.idle_gain * (self.idle_speed - speed)
            if idle_demand > demand:
                demand = idle_demand
            if speed > self.rev_limit:
                demand = 0.0
            demand = 0.0 if demand < 0.0 else (1.0 if demand > 1.0 else demand)
            self.load += (demand - self.load) * min(1.0, dt / self.response_time)
            indicated = self.load * indicated_max
            rate = indicated * speed / (self.efficiency * self.heating_value)
            self.fuel_rate = rate if rate > self.idle_fuel_rate else self.idle_fuel_rate
        else:
            self.load = 0.0
            indicated = 0.0
            self.fuel_rate = 0.0
        torque = indicated - friction
        if starter and speed < self.starter_cutoff:
            torque += self.starter_torque
        self.torque = torque
        self.fuel_used += self.fuel_rate * dt
