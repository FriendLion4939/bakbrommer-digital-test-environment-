"""Parameters: controller selection and the simple "direct" controller."""

from __future__ import annotations

from bakbrommer_twin.params.registry import Registry

# Ride modes in the order of the mode switch (index 0 is the power-on mode).
# To add a mode see docs/HOW_TO_CHANGE.md, "Add a ride mode".
RIDE_MODES: tuple[str, ...] = ("normal", "eco", "sport", "standalone_electric")

# Available controller implementations (see control/factory.py).
CONTROLLER_TYPES: tuple[str, ...] = ("direct",)


def register(reg: Registry) -> None:
    """Declare controller parameters."""
    reg.category("control", "Controller")
    reg.choice("control.controller_type", "direct", CONTROLLER_TYPES, "Controller",
               "direct: throttle goes straight to both motors, no hybrid logic "
               "(for testing the physics).")
    reg.number("control.loop_rate", 1000.0, "Hz", 10.0, 10000.0, "Control loop rate",
               "How often the controller runs (the STM32G4 loop frequency).")
    reg.number("control.direct.max_torque", 40.0, "Nm", 0.0, 200.0,
               "Direct controller: torque at full throttle",
               "Torque command per motor at full throttle.")
    reg.number("control.direct.regen_torque", 0.0, "Nm", 0.0, 200.0,
               "Direct controller: regen torque at full brake",
               "Braking torque command per motor at full front brake pressure.")
