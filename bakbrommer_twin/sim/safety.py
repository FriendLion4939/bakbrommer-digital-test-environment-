"""Safety monitor: watches a run and lists everything that went wrong, with times.

Each :class:`_Check` watches one quantity. While the quantity is above its
threshold an event is open; when it drops back the event is closed and kept
if it lasted long enough. The result is the list of :class:`SafetyEvent` in
the run's safety report.

To add a check: append one ``_Check(...)`` in ``SafetyMonitor.__init__`` and
add the texts ``event.<kind>`` to the translation file.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from bakbrommer_twin.params import units
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.physics import mass
from bakbrommer_twin.physics.motors import ElectricDrive
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.physics.wheels import FRONT_LEFT, FRONT_RIGHT, WHEEL_NAMES, Wheel


class SafetyEvent(BaseModel):
    """One entry of the safety report."""

    kind: str  # e.g. "wheel_lift"; translated in the UI as event.<kind>
    subject: str  # which wheel / motor ("" when not applicable)
    start: float  # s
    end: float  # s
    peak: float  # worst value during the event, in ``unit``
    unit: str  # friendly unit of ``peak``


@dataclass
class _Check:
    kind: str
    subject: str
    unit: str  # friendly unit for the report
    threshold: float  # SI; the event is active while value > threshold
    min_time: float  # s; shorter events are dropped
    value: Callable[[], float]  # SI
    sign: float = 1.0  # −1 for "too low" checks (value and threshold are negated)
    started: float = -1.0  # start time of the open event, −1 = none
    peak: float = 0.0


def _gap(wheel: Wheel) -> Callable[[], float]:
    return lambda: wheel.gap


def _slip(wheel: Wheel, min_speed: float, sign: float) -> Callable[[], float]:
    """Drive slip (sign +1) or brake slip (sign −1) of a loaded, moving wheel."""
    def value() -> float:
        moving = abs(wheel.v_long) > min_speed and wheel.load > 0.0
        return sign * wheel.tyre.kappa if moving else 0.0
    return value


def _slide(wheel: Wheel, min_speed: float) -> Callable[[], float]:
    """Slip angle magnitude of a loaded, moving wheel, rad."""
    def value() -> float:
        moving = abs(wheel.v_long) > min_speed and wheel.load > 0.0
        return abs(math.atan(wheel.tyre.tan_alpha)) if moving else 0.0
    return value


def _temperature(drive: ElectricDrive) -> Callable[[], float]:
    return lambda: drive.temperature


def rollover_margin(wheels: list[Wheel]) -> float:
    """1 = both front wheels equally loaded, 0 = one front wheel carries nothing.

    margin = 1 − |F_left − F_right| / (F_left + F_right)  (lateral load transfer
    ratio of the front axle). Returns 1 while both wheels are in the air.
    """
    left, right = wheels[FRONT_LEFT].load, wheels[FRONT_RIGHT].load
    total = left + right
    return 1.0 - abs(left - right) / total if total > 0.0 else 1.0


class SafetyMonitor:
    """Collects safety events during a run."""

    def __init__(self, params: ParamSet, vehicle: Vehicle) -> None:
        self.events: list[SafetyEvent] = []
        self.rolled_over = False
        self._vehicle = vehicle
        self._rollover_angle = params.num("safety.rollover_angle")
        min_speed = params.num("safety.min_speed_for_slip")
        battery, chassis = vehicle.battery, vehicle.chassis
        checks: list[_Check] = []
        for wheel in vehicle.wheels:
            name = WHEEL_NAMES[wheel.index]
            checks += [
                _Check("wheel_lift", name, "mm", params.num("safety.wheel_lift_min_height"),
                       params.num("safety.wheel_lift_min_time"), _gap(wheel)),
                _Check("wheel_spin", name, "%", params.num("safety.slip_ratio_limit"), 0.0,
                       _slip(wheel, min_speed, 1.0)),
                _Check("wheel_lock", name, "%", params.num("safety.lock_slip_limit"), 0.0,
                       _slip(wheel, min_speed, -1.0)),
                _Check("side_slide", name, "deg", params.num("safety.slip_angle_limit"), 0.0,
                       _slide(wheel, min_speed)),
            ]
        for side, drive in (("left", vehicle.drive_left), ("right", vehicle.drive_right)):
            checks += [
                _Check("motor_derating", side, "°C", drive.derate_start, 0.0,
                       _temperature(drive)),
                _Check("motor_overheat", side, "°C", drive.max_temperature, 0.0,
                       _temperature(drive)),
            ]
        checks += [
            _Check("battery_overcurrent", "", "A", battery.discharge_limit, 0.0,
                   lambda: battery.current),
            _Check("battery_overcharge", "", "A", battery.charge_limit, 0.0,
                   lambda: -battery.current),
            _Check("bms_trip", "", "", 0.5, 0.0, lambda: 0.0 if battery.connected else 1.0),
            _Check("battery_undervoltage", "", "V", -params.num("battery.min_voltage"), 0.0,
                   lambda: -battery.voltage, sign=-1.0),
            _Check("battery_overheat", "", "°C", params.num("battery.max_temperature"), 0.0,
                   lambda: battery.temperature),
            _Check("past_tip_over_point", "", "deg", mass.tip_over_angle(params), 0.0,
                   lambda: abs(chassis.roll)),
        ]
        self._checks = checks

    def update(self, time: float) -> None:
        """Evaluate all checks at ``time`` (s)."""
        for check in self._checks:
            value = check.value()
            if value > check.threshold:
                if check.started < 0.0:
                    check.started = time
                    check.peak = value
                elif value > check.peak:
                    check.peak = value
            elif check.started >= 0.0:
                self._close(check, time)
        chassis = self._vehicle.chassis
        if max(abs(chassis.roll), abs(chassis.pitch)) > self._rollover_angle:
            self.rolled_over = True

    def _close(self, check: _Check, time: float) -> None:
        if time - check.started >= check.min_time:
            self.events.append(SafetyEvent(
                kind=check.kind, subject=check.subject, start=check.started, end=time,
                peak=units.from_si(check.sign * check.peak, check.unit), unit=check.unit))
        check.started = -1.0

    def finish(self, time: float) -> None:
        """Close events that are still open at the end of the run."""
        for check in self._checks:
            if check.started >= 0.0:
                self._close(check, time)
        if self.rolled_over:
            chassis = self._vehicle.chassis
            angle = max(abs(chassis.roll), abs(chassis.pitch))
            self.events.append(SafetyEvent(kind="rollover", subject="", start=time, end=time,
                                           peak=units.from_si(angle, "deg"), unit="deg"))
        self.events.sort(key=lambda event: event.start)

    def has_open_or_recorded(self, kind: str, time: float) -> bool:
        """True if an event of ``kind`` was recorded or has been open long enough."""
        if any(event.kind == kind for event in self.events):
            return True
        return any(c.kind == kind and c.started >= 0.0 and time - c.started >= c.min_time
                   for c in self._checks)
