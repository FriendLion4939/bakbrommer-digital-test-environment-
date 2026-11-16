"""Petrol engine start/stop logic.

Decides whether the petrol engine should run (ride mode and speed), cranks it
with the starter when it should, and cuts the ignition when it is no longer
wanted. States: OFF → CRANKING → RUNNING → OFF.
"""

from __future__ import annotations

from bakbrommer_twin.control.reference.modes import ModeSettings
from bakbrommer_twin.params.paramset import ParamSet

OFF, CRANKING, RUNNING = 0, 1, 2


class EngineManager:
    """State machine for ignition and starter."""

    def __init__(self, params: ParamSet) -> None:
        self.auto = params.flag("control.engine_auto_start_stop")
        self.running_speed = params.num("control.engine_running_speed")
        self.crank_timeout = params.num("control.engine_crank_timeout")
        self.crank_pause = params.num("control.engine_crank_pause")
        self.stop_delay = params.num("control.engine_stop_delay")
        self.hysteresis = params.num("control.engine_speed_hysteresis")
        self.state = OFF
        self.ignition = False
        self.starter = False
        self._timer = 0.0  # s in the present state (cranking) or unwanted (running)
        self._pause = 0.0  # s the starter still has to rest

    def reset(self) -> None:
        """Power-on state."""
        self.state = OFF
        self.ignition = self.starter = False
        self._timer = self._pause = 0.0

    @property
    def running(self) -> bool:
        """True when the engine is running (as far as the controller can tell)."""
        return self.state == RUNNING

    def step(self, dt: float, mode: ModeSettings, speed: float, engine_speed: float) -> None:
        """Update ignition and starter for this control period."""
        turning = engine_speed > self.running_speed
        # Wanted above the start speed; once running, kept until clearly below it.
        threshold = mode.engine_start_speed
        if self.state == RUNNING:
            threshold -= self.hysteresis
        wanted = mode.engine_enabled and (speed >= threshold or mode.engine_start_speed <= 0.0)
        self.starter = False
        if not self.auto:  # the rider starts the engine; we only allow or forbid it
            self.ignition = mode.engine_enabled
            self.state = RUNNING if turning and self.ignition else OFF
            return
        if self._pause > 0.0:
            self._pause -= dt
        if self.state == OFF:
            self.ignition = wanted
            if wanted and turning:
                self.state = RUNNING
                self._timer = 0.0
            elif wanted and self._pause <= 0.0:
                self.state = CRANKING
                self._timer = 0.0
        elif self.state == CRANKING:
            self.ignition = True
            self.starter = True
            self._timer += dt
            if turning:
                self.state = RUNNING
                self._timer = 0.0
            elif not wanted or self._timer > self.crank_timeout:
                self.state = OFF
                self._pause = self.crank_pause
        else:  # RUNNING
            self.ignition = True
            if not turning:  # stalled
                self.state = OFF
                self._pause = self.crank_pause
            elif wanted:
                self._timer = 0.0
            else:
                self._timer += dt
                if self._timer > self.stop_delay:
                    self.state = OFF
                    self.ignition = False
