"""Builds the registry from one definition module per category.

To add a category: create a module with ``register(reg)`` and add it to
``_MODULES`` below (the order here is the order of the tabs in the UI).
"""

from __future__ import annotations

from bakbrommer_twin.params.definitions import (
    aero,
    battery,
    brakes,
    control,
    driver,
    engine,
    geometry,
    motor,
    sensors,
    sim,
    steering,
    wheels,
)
from bakbrommer_twin.params.registry import Registry

_MODULES = (geometry, wheels, steering, motor, battery, engine, brakes, aero, sensors,
            control, driver, sim)


def build_registry() -> Registry:
    """Create a registry containing every parameter of the program."""
    reg = Registry()
    for module in _MODULES:
        module.register(reg)
    return reg
