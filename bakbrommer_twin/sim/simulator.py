"""The simulation loop.

One :class:`Simulation` runs one scenario with one parameter set. Each step:

1. road: surface, gradient and bumps under the vehicle
2. rider (driver model, at its reaction rate): throttle, brakes, steering, gear
3. sensors: sample the true states (each at its own rate)
4. controller (at the control loop rate): sensor readings → commands
5. vehicle: advance the physics by one time step
6. at the recording rate: safety monitor, recorder, end conditions

See docs/ARCHITECTURE.md for the data flow.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import numpy as np

from bakbrommer_twin.control.factory import create_controller
from bakbrommer_twin.control.interface import Controller, ControllerInputs, ControllerOutputs
from bakbrommer_twin.params.definitions.control import RIDE_MODES
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.inputs import DriveCommands, Environment, RiderInputs
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.physics.wheels import REAR
from bakbrommer_twin.scenarios import metrics
from bakbrommer_twin.scenarios.driver import Driver, RouteDriver
from bakbrommer_twin.scenarios.route import Route
from bakbrommer_twin.scenarios.scenario import Scenario
from bakbrommer_twin.sensors.suite import SensorSuite
from bakbrommer_twin.sim.channels import build_channels
from bakbrommer_twin.sim.result import ChannelInfo, RunMeta, RunResult
from bakbrommer_twin.sim.road import Road
from bakbrommer_twin.sim.safety import SafetyMonitor
from bakbrommer_twin.sim.summary import summarise

ProgressCallback = Callable[[float], None]  # called with 0…1


def _every(rate: float, time_step: float) -> int:
    """Number of simulation steps between two events at ``rate`` (Hz), at least 1."""
    return max(1, round(1.0 / (rate * time_step)))


class Simulation:
    """Everything needed to run one scenario once."""

    def __init__(self, params: ParamSet, scenario: Scenario, *, profile_name: str = "",
                 validated: bool = False, name: str | None = None,
                 route: Route | None = None, driver: Driver | None = None,
                 controller: Controller | None = None) -> None:
        self.scenario = scenario
        self.params = params.with_display_overrides(scenario.param_overrides)
        p = self.params
        self.profile_name = profile_name
        self.validated = validated
        self.name = name or scenario.name
        self.dt = p.num("sim.time_step")
        self.vehicle = Vehicle(p)
        self.rider = RiderInputs()
        self.commands = DriveCommands()
        self.env = Environment(p.num("environment.air_temperature"))
        self.route = route or Route(scenario.route, p.num("sim.route_sample_spacing"),
                                    p.choice("environment.default_surface"))
        self.driver: Driver = driver or RouteDriver(p, self.route)
        self.road = Road(p, self.route, self.vehicle, self.env)
        self.sensors = SensorSuite(p, self.vehicle, self.rider, self.dt)
        self.controller = controller or create_controller(p)
        self.inputs = ControllerInputs()
        self.outputs = ControllerOutputs()
        self.safety = SafetyMonitor(p, self.vehicle)
        self._driver_every = _every(p.num("driver.update_rate"), self.dt)
        self._control_every = _every(p.num("control.loop_rate"), self.dt)
        self._log_every = _every(p.num("sim.log_rate"), self.dt)
        self._time_limit = min(scenario.end.time_limit_s, p.num("sim.max_duration"))
        self._stopped_speed = p.num("sim.stopped_speed")
        self._pending_events = list(scenario.events)
        self.time = 0.0
        self.step_index = 0
        self.distance = 0.0  # m along the route
        self.route_offset = 0.0  # m left of the route
        self._has_moved = False
        self._place_at_start()

    def _place_at_start(self) -> None:
        initial = self.scenario.initial
        speed = initial.speed_kmh / 3.6
        vehicle, route = self.vehicle, self.route
        driveline = vehicle.driveline
        gear = 1
        if not driveline.is_cvt:  # highest gear that keeps the engine above the downshift speed
            downshift = self.params.num("driver.downshift_speed")
            wheel_speed = speed / vehicle.wheels[REAR].radius
            for candidate in range(1, driveline.gear_count + 1):
                if wheel_speed * driveline.total_ratio(candidate) >= downshift:
                    gear = candidate
        vehicle.place(route.x[0], route.y[0], route.heading[0], speed, gear,
                      initial.engine_running)
        self.rider.gear = gear
        self.rider.mode_request = RIDE_MODES.index(initial.ride_mode)
        self.controller.reset()
        self.sensors.preset()

    # ---- the loop -------------------------------------------------------------------

    def run(self, progress: ProgressCallback | None = None) -> RunResult:
        """Run until an end condition is met and return the result."""
        dt = self.dt
        vehicle, rider, commands, env = self.vehicle, self.rider, self.commands, self.env
        road, driver, sensors, controller = self.road, self.driver, self.sensors, self.controller
        inputs, outputs = self.inputs, self.outputs
        driver_every, control_every, log_every = (self._driver_every, self._control_every,
                                                  self._log_every)
        driver_dt, control_dt = driver_every * dt, control_every * dt
        channels = build_channels(self)
        getters = [getter for _, getter in channels]
        columns: list[list[float]] = [[] for _ in channels]
        start_energy = vehicle.mechanical_energy()

        def record() -> None:
            for column, getter in zip(columns, getters, strict=True):
                column.append(getter())

        driver.update(driver_dt, vehicle, rider)
        self._track_route()
        record()
        end_reason = ""
        step = 0
        while not end_reason:
            road.update(dt, driver.route_index)
            if step % driver_every == 0:
                self._apply_events()
                driver.update(driver_dt, vehicle, rider)
            sensors.sample(step)
            if step % control_every == 0:
                sensors.fill(inputs)
                inputs.time = self.time
                inputs.dt = control_dt
                controller.step(inputs, outputs)
                commands.torque_left = outputs.torque_left
                commands.torque_right = outputs.torque_right
                commands.engine_throttle = outputs.engine_throttle
                commands.ignition = outputs.engine_ignition > 0.5
                commands.starter = outputs.engine_starter > 0.5
            vehicle.step(dt, rider, commands, env)
            step += 1
            self.step_index = step
            self.time = step * dt
            if step % log_every == 0:
                self._track_route()
                self.safety.update(self.time)
                record()
                end_reason = self._end_reason()
                if progress is not None:
                    progress(min(1.0, self.time / self._time_limit))

        self.safety.finish(self.time)
        data = {definition.name: np.array(column, dtype=np.float64)
                for (definition, _), column in zip(channels, columns, strict=True)}
        energy = vehicle.energy.as_dict()
        energy_error = vehicle.energy.mechanical_error(start_energy, vehicle.mechanical_energy())
        meta = RunMeta(
            name=self.name, scenario_name=self.scenario.name,
            scenario=self.scenario.model_dump(mode="json"), profile_name=self.profile_name,
            validated=self.validated, controller=self.params.choice("control.controller_type"),
            created=datetime.now().isoformat(timespec="seconds"), time_step=dt,
            duration=self.time, end_reason=end_reason, params=self.params.as_display_dict(),
            channels=[ChannelInfo.from_def(definition) for definition, _ in channels],
            events=self.safety.events, energy=energy,
            summary=summarise(data, self.safety.events, energy, energy_error, self.params),
            metrics=metrics.evaluate(self.scenario.metrics, data, self.safety.events),
        )
        return RunResult(meta, data)

    # ---- helpers ----------------------------------------------------------------------

    def _track_route(self) -> None:
        chassis = self.vehicle.chassis
        if self.route.has_path:
            self.distance, self.route_offset = self.route.project(
                self.driver.route_index, chassis.x, chassis.y)
        else:
            self.distance += abs(chassis.u) * self._log_every * self.dt

    def _apply_events(self) -> None:
        if not self._pending_events:
            return
        waiting = []
        for event in self._pending_events:
            due = (self.time >= event.at_time_s if event.at_time_s is not None
                   else self.distance >= (event.at_distance_m or 0.0))
            if due:
                self.rider.mode_request = RIDE_MODES.index(event.set_mode)
            else:
                waiting.append(event)
        self._pending_events = waiting

    def _end_reason(self) -> str:
        end = self.scenario.end
        speed = self.vehicle.chassis.u
        if abs(speed) > 10.0 * self._stopped_speed:
            self._has_moved = True
        if self.safety.rolled_over:
            return "rollover"
        if self.route.has_path and self.distance >= self.route.length:
            return "route_end"
        if end.at_speed_kmh is not None and speed >= end.at_speed_kmh / 3.6:
            return "speed_reached"
        if end.when_stopped and self._has_moved and abs(speed) < self._stopped_speed:
            return "stopped"
        if end.on_wheel_lift and self.safety.has_open_or_recorded("wheel_lift", self.time):
            return "wheel_lift"
        if self.time >= self._time_limit:
            return "time_limit"
        return ""


def run_scenario(params: ParamSet, scenario: Scenario, *, profile_name: str = "",
                 validated: bool = False, name: str | None = None,
                 progress: ProgressCallback | None = None) -> RunResult:
    """Convenience wrapper: build a :class:`Simulation` and run it."""
    return Simulation(params, scenario, profile_name=profile_name, validated=validated,
                      name=name).run(progress)
