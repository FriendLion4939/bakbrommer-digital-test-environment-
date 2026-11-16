"""The simulated rider: follows a route and a speed profile.

Speed plan
----------
Before the run a target speed is planned for every route sample:
1. the segment's target speed,
2. limited in corners to v = √(a_lat,max/|curvature|),
3. a backward pass so that every slow point can be reached with the planned
   braking: v[i] ≤ √(v[i+1]² + 2·a_brake·Δs).
Samples with a fixed throttle or brake are not speed-controlled and put no
limit on the plan. A planned halt (``stop_s`` on a segment) is a zero-speed
point; when the vehicle has stood there for the given time the point is
removed and the plan recalculated.

Speed control: the rider forms a wanted acceleration
    a = k_p·(v_target − v) + integral + planned deceleration (feed-forward)
and turns it into pedal positions: throttle = a / a_full_throttle, or brake
lever = −a / a_full_brake. ``a_full_brake`` is what the brakes would give at
full lever if no wheel locked (brake torques / wheel radii / mass) — the
rider knows the brakes.

Steering: "pure pursuit" (Coulter, CMU-RI-TR-92-01). The rider aims at a
point a preview distance L_d ahead on the route; the arc through that point
has curvature κ = 2·y_l/L_d² (y_l = sideways offset of the aim point in the
vehicle frame) and needs the steering angle δ = atan(wheelbase·κ). The rider
never steers harder than the cornering limit plus a correction margin allows
at the present speed: |κ| ≤ a_lat,max·(1 + margin)/v².

Wheel-lift reaction: when a front wheel is more than a set height off the
ground the rider steers out of the corner, in proportion to the extra lean
φ = (lift height − reaction height)/track and to the roll rate (a PD
controller, limited to a largest correction), closes the throttle and brakes
lightly. While reacting the rider also never asks for more cornering than the
vehicle can balance at its present lean: a_y ≤ g·tan(φ_tip − φ_lift) with
φ_lift = lift height/track (the lateral acceleration at which a rigid vehicle
is in balance on two wheels; φ_tip is the static tip-over angle from
``physics/mass.py``). For a recovery time after
touchdown the limit is the wheel-lift acceleration a_lift. Limits on a_y
become limits on steering through curvature = a_y/v². This is how a real
rider keeps a three-wheeler balanced on two wheels and brings the wheel back
down instead of rolling over. With the gain at zero the rider holds the line
regardless.

Gear changes (manual gearbox): shift up/down when the engine speed that the
present road speed would give crosses the shift speeds.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics import mass
from bakbrommer_twin.physics.brakes import Brakes
from bakbrommer_twin.physics.inputs import RiderInputs
from bakbrommer_twin.physics.mass import GRAVITY
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.physics.wheels import FRONT_LEFT, FRONT_RIGHT, REAR
from bakbrommer_twin.scenarios.route import Route


class Driver(Protocol):
    """Anything that can operate the rider inputs (route follower, log replay…)."""

    route_index: int
    target_speed: float

    def update(self, dt: float, vehicle: Vehicle, rider: RiderInputs) -> None:
        """Set throttle, brakes, steering and gear for the next ``dt`` seconds."""


def plan_speed(route: Route, max_lateral_accel: float, max_deceleration: float,
               halts: Sequence[int] = ()) -> list[float]:
    """Target speed (m/s) for every route sample; see the module docstring.

    ``halts`` are sample indices where the vehicle must come to a stop.
    """
    plan = []
    for i, (target, curvature) in enumerate(zip(route.speed, route.curvature, strict=True)):
        if not (math.isnan(route.throttle[i]) and math.isnan(route.brake[i])):
            plan.append(math.inf)  # fixed throttle/brake: no speed target here
            continue
        corner = math.sqrt(max_lateral_accel / abs(curvature)) if abs(curvature) > 0.0 else target
        plan.append(min(target, corner))
    for index in halts:
        plan[index] = 0.0
    for i in range(len(plan) - 2, -1, -1):
        reachable = math.sqrt(plan[i + 1] ** 2 + 2.0 * max_deceleration * route.spacing)
        if plan[i] > reachable:
            plan[i] = reachable
    return plan


class RouteDriver:
    """Follows the route with pure-pursuit steering and PI speed control."""

    def __init__(self, params: ParamSet, route: Route) -> None:
        self.route = route
        self.preview_time = params.num("driver.preview_time")
        self.min_preview = params.num("driver.min_preview_distance")
        self.speed_gain = params.num("driver.speed_gain")
        self.integral_gain = params.num("driver.speed_integral_gain")
        self.max_deceleration = params.num("driver.max_deceleration")
        self.full_throttle_accel = params.num("driver.full_throttle_acceleration")
        self.rear_brake_ratio = params.num("driver.rear_brake_ratio")
        # Deceleration at full front lever (rear lever following by its ratio) if no
        # wheel locked: a = (2·T_front/r_f + ratio·T_rear/r_r)/m.
        brakes = Brakes(params)
        rear_share = min(1.0, self.rear_brake_ratio)
        self.full_brake_decel = (
            2.0 * brakes.max_front_torque() / params.num("wheels.front_radius")
            + rear_share * brakes.max_rear_torque() / params.num("wheels.rear_radius")
        ) / mass.mass_properties(params).mass
        self.steer_rate = params.num("driver.steer_rate_limit")
        self.lift_height = params.num("driver.lift_reaction_height")
        self.track = params.num("geometry.front_track")
        self.lift_gain = params.num("driver.lift_reaction_gain")
        self.lift_damping = params.num("driver.lift_reaction_damping")
        self.lift_limit = params.num("driver.lift_reaction_limit")
        self.lift_brake = params.num("driver.lift_reaction_brake")
        self.lift_recovery = params.num("driver.lift_recovery_time")
        # Cornering acceleration at which a front wheel lifts (the rider knows the machine).
        self.lift_accel = min(mass.lift_threshold_accel(params, turn_left=True),
                              mass.lift_threshold_accel(params, turn_left=False))
        self.tip_angle = mass.tip_over_angle(params)
        self.reacting_to_lift = False
        self._recovery_left = 0.0  # s of careful cornering still to go
        self.upshift = params.num("driver.upshift_speed")
        self.downshift = params.num("driver.downshift_speed")
        self.wheelbase = params.num("geometry.wheelbase")
        self.steering_ratio = params.num("steering.ratio")
        self.max_handlebar = params.num("steering.max_angle") * self.steering_ratio
        self.max_lateral_accel = params.num("driver.max_lateral_accel")
        self.steering_accel = self.max_lateral_accel * (
            1.0 + params.num("driver.correction_margin"))
        self.stopped_speed = params.num("sim.stopped_speed")
        self._halts = list(route.stops)  # planned halts still ahead
        self._waited = 0.0  # s spent standing at the present halt
        self.plan = self._make_plan()
        self.route_index = 0
        self.target_speed = self.plan[0]
        self._integral = 0.0

    def _make_plan(self) -> list[float]:
        return plan_speed(self.route, self.max_lateral_accel, self.max_deceleration,
                          [index for index, _ in self._halts])

    def _wait_at_halt(self, dt: float, index: int, speed: float) -> None:
        """Count the standing time at a planned halt and move on when it is over."""
        halt_index, duration = self._halts[0]
        if index >= halt_index - 1 and abs(speed) < self.stopped_speed:
            self._waited += dt
            if self._waited >= duration:
                self._halts.pop(0)
                self._waited = 0.0
                self.plan = self._make_plan()

    def update(self, dt: float, vehicle: Vehicle, rider: RiderInputs) -> None:
        """Set the rider inputs from the vehicle's position and speed."""
        chassis, route = vehicle.chassis, self.route
        index = route.locate(chassis.x, chassis.y, self.route_index)
        self.route_index = index
        speed = chassis.u
        if self._halts:
            self._wait_at_halt(dt, index, speed)
        self._steer(dt, vehicle, rider, index, speed)
        self._pedals(dt, rider, index, speed)
        self._gears(vehicle, rider)

    def _steer(self, dt: float, vehicle: Vehicle, rider: RiderInputs, index: int,
               speed: float) -> None:
        chassis, route = vehicle.chassis, self.route
        preview = max(self.min_preview, self.preview_time * abs(speed))
        aim = min(len(route) - 1, index + max(1, round(preview / route.spacing)))
        dx, dy = route.x[aim] - chassis.x, route.y[aim] - chassis.y
        beyond = preview - (route.s[aim] - route.s[index])
        if beyond > route.spacing:  # past the end: aim along the final direction
            dx += beyond * math.cos(route.heading[aim])
            dy += beyond * math.sin(route.heading[aim])
        cos_y, sin_y = math.cos(chassis.yaw), math.sin(chassis.yaw)
        local_x = cos_y * dx + sin_y * dy
        local_y = cos_y * dy - sin_y * dx
        distance_sq = local_x * local_x + local_y * local_y
        curvature = 2.0 * local_y / distance_sq if distance_sq > 0.0 else 0.0
        if speed != 0.0:
            hardest = self.steering_accel / (speed * speed)
            curvature = max(-hardest, min(hardest, curvature))
        # Wheel-lift reaction (see module docstring). A lifted left wheel belongs to
        # a left turn (positive curvature, positive roll): side = +1; right: −1.
        gap_left, gap_right = vehicle.wheels[FRONT_LEFT].gap, vehicle.wheels[FRONT_RIGHT].gap
        gap, side = (gap_left, 1.0) if gap_left >= gap_right else (gap_right, -1.0)
        reacting = gap > self.lift_height and self.lift_gain > 0.0
        self.reacting_to_lift = reacting
        if reacting:
            self._recovery_left = self.lift_recovery
        elif self._recovery_left > 0.0:
            self._recovery_left -= dt
        if reacting and speed != 0.0:
            balance = GRAVITY * math.tan(self.tip_angle - gap / self.track) / (speed * speed)
            curvature = min(curvature, balance) if side > 0.0 else max(curvature, -balance)
        elif self._recovery_left > 0.0 and speed != 0.0:
            gentle = self.lift_accel / (speed * speed)  # stays below the wheel-lift limit
            curvature = max(-gentle, min(gentle, curvature))
        wanted = math.atan(self.wheelbase * curvature) * self.steering_ratio
        if reacting:
            lean = side * (gap - self.lift_height) / self.track  # extra roll angle, rad
            correction = self.lift_gain * lean + self.lift_damping * chassis.p
            wanted -= max(-self.lift_limit, min(self.lift_limit, correction))
        wanted = max(-self.max_handlebar, min(self.max_handlebar, wanted))
        change = wanted - rider.steer
        limit = self.steer_rate * dt
        rider.steer += max(-limit, min(limit, change))

    def _pedals(self, dt: float, rider: RiderInputs, index: int, speed: float) -> None:
        route = self.route
        fixed_throttle, fixed_brake = route.throttle[index], route.brake[index]
        if fixed_throttle == fixed_throttle or fixed_brake == fixed_brake:  # not nan
            throttle = fixed_throttle if fixed_throttle == fixed_throttle else 0.0
            brake = fixed_brake if fixed_brake == fixed_brake else 0.0
            self.target_speed = route.speed[index]
            self._integral = 0.0
        else:
            ahead = min(len(route) - 1, index + 1)
            target = self.plan[index]
            self.target_speed = target
            # Planned acceleration along the route: a = v·dv/ds (none into a fixed-pedal part).
            step = self.plan[ahead] - target
            planned_accel = target * step / route.spacing if step < 0.0 else 0.0
            error = target - speed
            # Integrate only while the pedals are not at their stop (anti-windup).
            if not (rider.throttle >= 1.0 and error > 0.0) and not (
                    rider.brake_front >= 1.0 and error < 0.0):
                self._integral += self.integral_gain * self.speed_gain * error * dt
            limit = self.full_throttle_accel
            self._integral = max(-limit, min(limit, self._integral))
            wanted = self.speed_gain * error + self._integral + planned_accel  # m/s²
            if target <= 0.0:  # planned stop: brake at least as planned and hold
                wanted = min(wanted, -self.max_deceleration)
            throttle = max(0.0, min(1.0, wanted / self.full_throttle_accel))
            brake = max(0.0, min(1.0, -wanted / self.full_brake_decel))
        if self.reacting_to_lift:  # wheel in the air: off the throttle, light braking
            throttle = 0.0
            brake = max(brake, self.lift_brake)
        rider.throttle = throttle
        rider.brake_front = brake
        rider.brake_rear = min(1.0, brake * self.rear_brake_ratio)

    def _gears(self, vehicle: Vehicle, rider: RiderInputs) -> None:
        shift_gears(vehicle, rider, self.upshift, self.downshift)


def shift_gears(vehicle: Vehicle, rider: RiderInputs, upshift: float, downshift: float) -> None:
    """Gear lever logic of a rider on a manual gearbox (does nothing for a CVT).

    Shifts up/down when the engine speed belonging to the present road speed
    crosses the shift speeds, and closes the throttle during the change.
    """
    driveline = vehicle.driveline
    if driveline.is_cvt:
        return
    if driveline.shifting:
        if vehicle.engine.running:
            rider.throttle = 0.0  # the rider closes the throttle while changing gear
        return
    gear = driveline.gear
    if gear == 0:
        rider.gear = 1
        return
    locked_speed = abs(vehicle.wheels[REAR].omega) * driveline.total_ratio(gear)
    if locked_speed > upshift and gear < driveline.gear_count:
        rider.gear = gear + 1
    elif locked_speed < downshift and gear > 1:
        rider.gear = gear - 1
    else:
        rider.gear = gear
