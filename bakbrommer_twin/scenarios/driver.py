"""The simulated rider: follows a route and a speed profile.

Speed plan
----------
Before the run a target speed is planned for every route sample:
1. the segment's target speed,
2. limited in corners to v = √(a_lat,max/|curvature|),
3. a backward pass so that every slow point can be reached with the planned
   braking: v[i] ≤ √(v[i+1]² + 2·a_brake·Δs).
Samples with a fixed throttle or brake are not speed-controlled and put no
limit on the plan.

Speed control: PI controller on the speed error plus a feed-forward from the
planned deceleration. Positive output = throttle, negative = brake.

Steering: "pure pursuit" (Coulter, CMU-RI-TR-92-01). The rider aims at a
point a preview distance L_d ahead on the route; the arc through that point
has curvature κ = 2·y_l/L_d² (y_l = sideways offset of the aim point in the
vehicle frame) and needs the steering angle δ = atan(wheelbase·κ).

Wheel-lift reaction: when the vehicle leans beyond a set roll angle (a front
wheel is in the air) the rider steers out of the corner, in proportion to the
excess roll angle and the roll rate (a PD controller on roll, limited to a
largest correction), closes the throttle and brakes lightly. While reacting,
and for a recovery time afterwards, the rider also does not ask for more
cornering than the vehicle's wheel-lift limit (steering curvature ≤
a_lift/v², with a_lift from ``physics/mass.py``). This is how a real rider
keeps a three-wheeler balanced on two wheels and brings the wheel back down
instead of rolling over. With the gain at zero the rider holds the line
regardless.

Gear changes (manual gearbox): shift up/down when the engine speed that the
present road speed would give crosses the shift speeds.
"""

from __future__ import annotations

import math
from typing import Protocol

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics import mass
from bakbrommer_twin.physics.inputs import RiderInputs
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.physics.wheels import REAR
from bakbrommer_twin.scenarios.route import Route


class Driver(Protocol):
    """Anything that can operate the rider inputs (route follower, log replay…)."""

    route_index: int
    target_speed: float

    def update(self, dt: float, vehicle: Vehicle, rider: RiderInputs) -> None:
        """Set throttle, brakes, steering and gear for the next ``dt`` seconds."""


def plan_speed(route: Route, max_lateral_accel: float, max_deceleration: float) -> list[float]:
    """Target speed (m/s) for every route sample; see the module docstring."""
    plan = []
    for i, (target, curvature) in enumerate(zip(route.speed, route.curvature, strict=True)):
        if not (math.isnan(route.throttle[i]) and math.isnan(route.brake[i])):
            plan.append(math.inf)  # fixed throttle/brake: no speed target here
            continue
        corner = math.sqrt(max_lateral_accel / abs(curvature)) if abs(curvature) > 0.0 else target
        plan.append(min(target, corner))
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
        self.full_brake_decel = params.num("driver.full_brake_deceleration")
        self.rear_brake_ratio = params.num("driver.rear_brake_ratio")
        self.steer_rate = params.num("driver.steer_rate_limit")
        self.lift_roll = params.num("driver.lift_reaction_roll")
        self.lift_gain = params.num("driver.lift_reaction_gain")
        self.lift_damping = params.num("driver.lift_reaction_damping")
        self.lift_limit = params.num("driver.lift_reaction_limit")
        self.lift_brake = params.num("driver.lift_reaction_brake")
        self.lift_recovery = params.num("driver.lift_recovery_time")
        # Cornering acceleration at which a front wheel lifts (the rider knows the machine).
        self.lift_accel = min(mass.lift_threshold_accel(params, turn_left=True),
                              mass.lift_threshold_accel(params, turn_left=False))
        self.reacting_to_lift = False
        self._recovery_left = 0.0  # s of careful cornering still to go
        self.upshift = params.num("driver.upshift_speed")
        self.downshift = params.num("driver.downshift_speed")
        self.wheelbase = params.num("geometry.wheelbase")
        self.steering_ratio = params.num("steering.ratio")
        self.max_handlebar = params.num("steering.max_angle") * self.steering_ratio
        self.plan = plan_speed(route, params.num("driver.max_lateral_accel"),
                               self.max_deceleration)
        self.route_index = 0
        self.target_speed = self.plan[0]
        self._integral = 0.0

    def update(self, dt: float, vehicle: Vehicle, rider: RiderInputs) -> None:
        """Set the rider inputs from the vehicle's position and speed."""
        chassis, route = vehicle.chassis, self.route
        index = route.locate(chassis.x, chassis.y, self.route_index)
        self.route_index = index
        speed = chassis.u
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
        # Wheel-lift reaction (see module docstring). Positive roll = left side up.
        roll = chassis.roll
        reacting = abs(roll) > self.lift_roll and self.lift_gain > 0.0
        self.reacting_to_lift = reacting
        if reacting:
            self._recovery_left = self.lift_recovery
        elif self._recovery_left > 0.0:
            self._recovery_left -= dt
        if (reacting or self._recovery_left > 0.0) and speed != 0.0:
            gentle = self.lift_accel / (speed * speed)  # curvature that stays below the limit
            curvature = max(-gentle, min(gentle, curvature))
        wanted = math.atan(self.wheelbase * curvature) * self.steering_ratio
        if reacting:
            excess = roll - self.lift_roll if roll > 0.0 else roll + self.lift_roll
            correction = self.lift_gain * excess + self.lift_damping * chassis.p
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
            self._integral += self.integral_gain * error * dt
            self._integral = max(-1.0, min(1.0, self._integral))
            command = self.speed_gain * error + self._integral
            if planned_accel < 0.0:
                command += planned_accel / self.full_brake_decel
            if target <= 0.0:  # planned stop: brake at least as planned and hold
                command = min(command, -self.max_deceleration / self.full_brake_decel)
            throttle = max(0.0, min(1.0, command))
            brake = max(0.0, min(1.0, -command))
        if self.reacting_to_lift:  # wheel in the air: off the throttle, light braking
            throttle = 0.0
            brake = max(brake, self.lift_brake)
        rider.throttle = throttle
        rider.brake_front = brake
        rider.brake_rear = min(1.0, brake * self.rear_brake_ratio)

    def _gears(self, vehicle: Vehicle, rider: RiderInputs) -> None:
        driveline = vehicle.driveline
        if driveline.is_cvt:
            return
        if driveline.shifting:
            rider.throttle = 0.0  # the rider closes the throttle while changing gear
            return
        gear = driveline.gear
        if gear == 0:
            rider.gear = 1
            return
        locked_speed = abs(vehicle.wheels[REAR].omega) * driveline.total_ratio(gear)
        if locked_speed > self.upshift and gear < driveline.gear_count:
            rider.gear = gear + 1
        elif locked_speed < self.downshift and gear > 1:
            rider.gear = gear - 1
        else:
            rider.gear = gear
