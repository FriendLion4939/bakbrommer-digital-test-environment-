"""The complete vehicle ("plant"): all subsystems wired together.

One call of :meth:`Vehicle.step` advances everything by one time step, in
this order (see docs/ARCHITECTURE.md, "One simulation step"):

1. steering geometry and brake pressures from the rider inputs
2. wheel contact: loads and contact-point velocities (chassis)
3. tyre slip states and tyre forces
4. electric drives (torque, current, heat), then the battery
5. friction capacities; front wheel spin
6. petrol engine torque; clutch/gearbox solver for engine + rear wheel
7. air forces and gravity; rigid-body integration (chassis)
8. energy bookkeeping
"""

from __future__ import annotations

import math

from bakbrommer_twin.params.definitions.wheels import SURFACE_NAMES
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics import mass
from bakbrommer_twin.physics.aero import Aero
from bakbrommer_twin.physics.battery import Battery
from bakbrommer_twin.physics.brakes import Brakes
from bakbrommer_twin.physics.chassis import Chassis
from bakbrommer_twin.physics.energy import EnergyLedger
from bakbrommer_twin.physics.engine import Engine
from bakbrommer_twin.physics.gearbox import Driveline
from bakbrommer_twin.physics.inputs import DriveCommands, Environment, RiderInputs
from bakbrommer_twin.physics.motors import ElectricDrive
from bakbrommer_twin.physics.steering import Steering
from bakbrommer_twin.physics.surfaces import load_surfaces
from bakbrommer_twin.physics.tyres import Tyre
from bakbrommer_twin.physics.wheels import FRONT_LEFT, FRONT_RIGHT, REAR, Wheel


class Vehicle:
    """All physics subsystems of the bakbrommer and their interaction."""

    def __init__(self, params: ParamSet) -> None:
        self.props = mass.mass_properties(params)
        self.surfaces = load_surfaces(params)
        self.chassis = Chassis(self.props)
        self.steering = Steering(params)
        self.brakes = Brakes(params)
        self.aero = Aero(params, self.props)
        self.drive_left = ElectricDrive(params)
        self.drive_right = ElectricDrive(params)
        self.battery = Battery(params)
        self.engine = Engine(params)
        self.driveline = Driveline(params)
        self.energy = EnergyLedger()
        self.throttle_by_wire = params.flag("engine.throttle_by_wire")
        self.rolling_speed_factor = params.num("tyre.rolling_resistance_speed_factor")
        self.wheels = self._build_wheels(params)
        self.steering.apply(0.0, self.wheels)
        self.engine_throttle = 0.0  # throttle that reached the engine this step, 0…1

    def _build_wheels(self, params: ParamSet) -> list[Wheel]:
        props = self.props
        wheelbase = params.num("geometry.wheelbase")
        half_track = params.num("geometry.front_track") / 2.0
        loads = mass.static_wheel_loads(params)
        surface = self.surfaces[SURFACE_NAMES[0]]
        wheels = []
        # (axle, x ahead of the CoG, y left of the CoG) for FL, FR, rear
        layout = (("front", props.cog_x, half_track - props.cog_y),
                  ("front", props.cog_x, -half_track - props.cog_y),
                  ("rear", props.cog_x - wheelbase, -props.cog_y))
        for index, (axle, x, y) in enumerate(layout):
            wheel = Wheel(index, params.num(f"wheels.{axle}_radius"),
                          params.num(f"wheels.{axle}_inertia"),
                          params.num(f"suspension.{axle}_stiffness"),
                          params.num(f"suspension.{axle}_damping"), Tyre(params, axle), surface)
            wheel.base_x = wheel.x = x
            wheel.base_y = wheel.y = y
            wheel.static_load = loads[index]
            # The unloaded tyre bottom sits below the road by the static spring
            # compression F/k, so that at rest the CoG is exactly at its height.
            wheel.z_foot = -(props.cog_height + loads[index] / wheel.stiffness)
            wheels.append(wheel)
        return wheels

    # ---- setting up the start of a run ----------------------------------------------

    def place(self, x: float, y: float, heading: float, speed: float, gear: int,
              engine_running: bool) -> None:
        """Put the vehicle on the road at rest equilibrium, moving at ``speed`` (m/s)."""
        chassis = self.chassis
        chassis.x, chassis.y, chassis.yaw = x, y, heading
        chassis.z = self.props.cog_height
        chassis.pitch = chassis.roll = 0.0
        chassis.u, chassis.v, chassis.w = speed, 0.0, 0.0
        chassis.p = chassis.q = chassis.r = 0.0
        for wheel in self.wheels:
            wheel.omega = speed / wheel.radius
            wheel.tyre.reset()
        self.driveline.select_gear(gear)
        if engine_running:
            self.engine.start_running()
            locked_speed = self.wheels[REAR].omega * self.driveline.ratio
            if locked_speed > self.engine.speed:
                self.engine.speed = locked_speed
        else:
            self.engine.speed = 0.0
            self.engine.running = False

    # ---- one time step -------------------------------------------------------------------

    def step(self, dt: float, rider: RiderInputs, commands: DriveCommands,
             env: Environment) -> None:
        """Advance the whole vehicle by ``dt`` seconds."""
        chassis, wheels = self.chassis, self.wheels
        front_left, front_right, rear = wheels[FRONT_LEFT], wheels[FRONT_RIGHT], wheels[REAR]
        brakes, battery, engine, driveline = self.brakes, self.battery, self.engine, self.driveline

        self.steering.apply(rider.steer, wheels)
        brakes.update(dt, rider.brake_front, rider.brake_rear)
        chassis.update_rotation()
        chassis.contacts(wheels)
        for wheel in wheels:
            wheel.tyre.update(dt, wheel.v_long, wheel.v_lat, wheel.omega * wheel.radius,
                              wheel.load, wheel.surface)

        air = env.air_temperature
        left, right = self.drive_left, self.drive_right
        left.step(dt, commands.torque_left, front_left.omega, battery.voltage,
                  battery.connected, air)
        right.step(dt, commands.torque_right, front_right.omega, battery.voltage,
                   battery.connected, air)
        bus_voltage = battery.voltage
        motor_current = left.bus_current + right.bus_current
        battery.step(dt, motor_current, air)

        # Friction capacities: brake + rolling resistance (+ motor or driveline drag).
        # Rolling resistance moment = c_rr·(1 + k·v²)·F_z·r (SAE J2452-style speed term).
        speed_factor = self.rolling_speed_factor
        rolling = [0.0, 0.0, 0.0]
        for wheel in wheels:
            v = wheel.v_long
            rolling[wheel.index] = (wheel.surface.rolling_resistance
                                    * (1.0 + speed_factor * v * v) * wheel.load * wheel.radius)
        front_left.friction_capacity = brakes.front_torque + rolling[0] + left.drag_torque
        front_right.friction_capacity = brakes.front_torque + rolling[1] + right.drag_torque
        rear.friction_capacity = brakes.rear_torque + rolling[2] + driveline.drag_torque
        front_left.drive_torque = left.torque
        front_right.drive_torque = right.torque
        front_left.spin(dt)
        front_right.spin(dt)

        throttle = commands.engine_throttle if self.throttle_by_wire else rider.throttle
        self.engine_throttle = throttle
        engine.update(dt, throttle, commands.ignition, commands.starter)
        driveline.update(dt, rider.gear, engine.speed, rear.omega, throttle)
        engine_torque = engine.torque
        engine.speed, rear.omega = driveline.solve(
            dt, engine.speed, engine_torque, engine.inertia, rear.omega,
            rear.effective_inertia(dt), -rear.radius * rear.tyre.fx, rear.friction_capacity)
        rear.drive_torque = driveline.wheel_torque
        rear.friction_torque = driveline.friction_torque

        # Wind and gravity in the level frame (world frame turned by the yaw angle).
        cos_y, sin_y = math.cos(chassis.yaw), math.sin(chassis.yaw)
        self.aero.update(chassis.u, chassis.v, cos_y * env.wind_x + sin_y * env.wind_y,
                         cos_y * env.wind_y - sin_y * env.wind_x)
        # Gravity tilted by the gradient: the in-plane part points downhill.
        downhill = -mass.GRAVITY * env.grade_sin
        uphill_angle = env.route_heading - chassis.yaw
        chassis.integrate(dt, wheels, downhill * math.cos(uphill_angle),
                          downhill * math.sin(uphill_angle),
                          -mass.GRAVITY * env.grade_cos, self.aero)

        self._account(dt, rolling, bus_voltage, motor_current, engine_torque)

    def _account(self, dt: float, rolling: list[float], bus_voltage: float,
                 motor_current: float, engine_torque: float) -> None:
        """Add this step's energy flows to the ledger."""
        ledger, brakes, battery, engine = self.energy, self.brakes, self.battery, self.engine
        left, right, driveline = self.drive_left, self.drive_right, self.driveline
        tyre_power = 0.0
        for wheel, drive, brake in ((self.wheels[0], left.drag_torque, brakes.front_torque),
                                    (self.wheels[1], right.drag_torque, brakes.front_torque),
                                    (self.wheels[2], driveline.drag_torque, brakes.rear_torque)):
            tyre = wheel.tyre
            omega = wheel.omega
            # Tyre slip power: force × sliding velocity of the contact patch.
            tyre_power += tyre.fx * (omega * wheel.radius - wheel.v_long) - tyre.fy * wheel.v_lat
            capacity = wheel.friction_capacity
            if capacity > 0.0:
                # Split the applied friction torque by the share of each source.
                friction_energy = wheel.friction_torque * omega * dt / capacity
                ledger.brake_loss += friction_energy * brake
                ledger.rolling_loss += friction_energy * rolling[wheel.index]
                ledger.drag_loss += friction_energy * drive
        ledger.tyre_loss += tyre_power * dt
        ledger.motor_work += (left.torque * self.wheels[0].omega
                              + right.torque * self.wheels[1].omega) * dt
        ledger.engine_work += engine_torque * engine.speed * dt
        ledger.gravity_work += self.chassis.gravity_power * dt
        ledger.clutch_loss += driveline.clutch_loss * dt
        ledger.gear_loss += driveline.gear_loss * dt
        ledger.aero_loss += self.aero.power * dt
        ledger.damper_loss += self.chassis.damper_power * dt
        ledger.battery_chemical += battery.chemical_power * dt
        ledger.battery_loss += battery.loss_power * dt
        bus_power = bus_voltage * motor_current
        ledger.bus_energy += bus_power * dt
        if bus_power < 0.0:
            ledger.regen_energy -= bus_power * dt
        if battery.connected:
            ledger.aux_energy += battery.aux_power * dt
        ledger.motor_loss += (left.copper_loss + right.copper_loss) * dt
        ledger.fuel_energy += engine.fuel_rate * engine.heating_value * dt

    # ---- read-outs ----------------------------------------------------------------------

    def mechanical_energy(self) -> float:
        """Kinetic energy of body, wheels and engine plus spring energy, J."""
        energy = self.chassis.kinetic_energy()
        energy += 0.5 * self.engine.inertia * self.engine.speed**2
        for wheel in self.wheels:
            energy += 0.5 * wheel.inertia * wheel.omega**2
            energy += 0.5 * wheel.stiffness * wheel.compression**2
        return energy

    def speed(self) -> float:
        """Forward speed of the centre of gravity, m/s."""
        return self.chassis.u
