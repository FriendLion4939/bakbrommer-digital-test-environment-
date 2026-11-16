"""Torque vectoring: how the drive torque is shared between left and right.

Two parts:

1. Load-proportional split (feed-forward). In a corner the outer wheel
   carries more load, so it can transmit more torque. A share
   ``gain·a_y/g`` of the torque is moved from the inner to the outer wheel
   (a_y = measured sideways acceleration). This also pushes the vehicle into
   the turn and stops the lightly loaded inner wheel from spinning.

2. Yaw rate correction (feedback). The yaw rate a neutral vehicle would have
   is r_ref = v·tan(δ)/(L·(1 + K·v²)) (single-track model with understeer
   gradient K, e.g. Rajamani, "Vehicle Dynamics and Control", §8), limited
   to a_y,max/v. A torque difference k·(r_ref − r) nudges the vehicle
   towards it.

Sign convention: positive values turn left (more torque on the right wheel).
"""

from __future__ import annotations

import math

from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics.mass import GRAVITY


class TorqueVectoring:
    """Splits one torque request into left and right wheel torques."""

    def __init__(self, params: ParamSet) -> None:
        self.enabled = params.flag("control.vectoring.enabled")
        self.split_gain = params.num("control.vectoring.load_split_gain")
        self.yaw_gain = params.num("control.vectoring.yaw_gain")
        self.max_difference = params.num("control.vectoring.max_torque_difference")
        self.understeer = params.num("control.vectoring.understeer_gradient")
        self.max_lateral = params.num("control.vectoring.max_lateral_accel")
        self.wheelbase = params.num("geometry.wheelbase")
        self.steering_ratio = params.num("steering.ratio")
        self.left = 0.0  # Nm
        self.right = 0.0  # Nm
        self.yaw_reference = 0.0  # rad/s

    def step(self, torque: float, speed: float, handlebar: float, yaw_rate: float,
             lateral_accel: float) -> None:
        """Compute ``left``/``right`` for a per-wheel ``torque`` request (Nm)."""
        if not self.enabled:
            self.left = self.right = torque
            return
        share = self.split_gain * lateral_accel / GRAVITY
        share = 1.0 if share > 1.0 else (-1.0 if share < -1.0 else share)
        # Yaw rate reference from steering angle and speed.
        reference = speed * math.tan(handlebar / self.steering_ratio) / (
            self.wheelbase * (1.0 + self.understeer * speed * speed))
        if speed > 0.0:
            limit = self.max_lateral / speed
            reference = limit if reference > limit else (-limit if reference < -limit
                                                         else reference)
        self.yaw_reference = reference
        correction = self.yaw_gain * (reference - yaw_rate)
        limit = self.max_difference
        correction = limit if correction > limit else (-limit if correction < -limit
                                                       else correction)
        if torque <= 0.0:
            correction = 0.0  # yaw correction only while driving; regen keeps the load split
        self.left = torque * (1.0 - share) - 0.5 * correction
        self.right = torque * (1.0 + share) + 0.5 * correction
        if torque > 0.0:  # a driving request never turns into braking on one side
            if self.left < 0.0:
                self.left = 0.0
            if self.right < 0.0:
                self.right = 0.0
