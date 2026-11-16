"""Ride modes and gliding from one mode to another.

Each mode is a set of numbers (:class:`ModeSettings`). When the rider turns
the mode switch, the numbers in effect glide linearly from the old mode to
the new one over the blend time, so the torque never jumps.
"""

from __future__ import annotations

from bakbrommer_twin.params.definitions.control import RIDE_MODES
from bakbrommer_twin.params.paramset import ParamSet

# Numeric settings of a mode (parameter key = attribute name).
NUMERIC_FIELDS: tuple[str, ...] = (
    "electric_torque", "throttle_exponent", "electric_fade_start", "electric_fade_end",
    "coast_regen_torque", "brake_regen_torque", "engine_start_speed", "engine_throttle_gain",
    "current_limit_share",
)


class ModeSettings:
    """The settings of one ride mode (or the blend currently in effect)."""

    __slots__ = (*NUMERIC_FIELDS, "engine_enabled")

    def __init__(self) -> None:
        self.electric_torque = 0.0  # Nm per motor at full throttle
        self.throttle_exponent = 1.0
        self.electric_fade_start = 0.0  # m/s
        self.electric_fade_end = 1.0  # m/s
        self.coast_regen_torque = 0.0  # Nm per motor
        self.brake_regen_torque = 0.0  # Nm per motor at full brake
        self.engine_start_speed = 0.0  # m/s
        self.engine_throttle_gain = 1.0
        self.current_limit_share = 1.0
        self.engine_enabled = True

    @classmethod
    def from_params(cls, params: ParamSet, mode: str) -> ModeSettings:
        """Read one mode's settings from the parameters."""
        settings = cls()
        for name in NUMERIC_FIELDS:
            setattr(settings, name, params.num(f"control.mode_{mode}.{name}"))
        settings.engine_enabled = params.flag(f"control.mode_{mode}.engine_enabled")
        if settings.electric_fade_end <= settings.electric_fade_start:
            raise ValueError(f"control.mode_{mode}: electric_fade_end must be above "
                             "electric_fade_start")
        return settings

    def copy_from(self, other: ModeSettings) -> None:
        """Take over all values of ``other``."""
        for name in NUMERIC_FIELDS:
            setattr(self, name, getattr(other, name))
        self.engine_enabled = other.engine_enabled


class ModeManager:
    """Keeps track of the active ride mode and the blended settings in effect."""

    def __init__(self, params: ParamSet) -> None:
        self.table = [ModeSettings.from_params(params, mode) for mode in RIDE_MODES]
        self.blend_time = params.num("control.mode_blend_time")
        self.active = 0  # index of the mode being blended towards
        self.current = ModeSettings()  # settings in effect right now
        self._start = ModeSettings()  # settings when the present blend began
        self._progress = 1.0  # 0 → 1 during a blend
        self.reset()

    def reset(self) -> None:
        """Power-on state: the first mode, fully in effect."""
        self.active = 0
        self._progress = 1.0
        self.current.copy_from(self.table[0])

    def step(self, dt: float, requested: float) -> ModeSettings:
        """Follow the mode switch and return the settings in effect."""
        wanted = min(len(self.table) - 1, max(0, round(requested)))
        if wanted != self.active:
            self.active = wanted
            self._start.copy_from(self.current)
            self._progress = 0.0 if self.blend_time > 0.0 else 1.0
            if self._progress >= 1.0:
                self.current.copy_from(self.table[wanted])
            self.current.engine_enabled = self.table[wanted].engine_enabled
        if self._progress < 1.0:
            self._progress = min(1.0, self._progress + dt / self.blend_time)
            target, start, current = self.table[self.active], self._start, self.current
            for name in NUMERIC_FIELDS:
                begin = getattr(start, name)
                setattr(current, name, begin + (getattr(target, name) - begin) * self._progress)
        return self.current
