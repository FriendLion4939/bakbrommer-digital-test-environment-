"""Creates the controller selected by ``control.controller_type``.

To add a controller implementation: write a class with ``reset()`` and
``step(inputs, outputs)``, add its name to ``CONTROLLER_TYPES`` in
``params/definitions/control.py`` and a line to ``_BUILDERS`` here.
"""

from __future__ import annotations

from collections.abc import Callable

from bakbrommer_twin.control.direct import DirectController
from bakbrommer_twin.control.interface import Controller
from bakbrommer_twin.params.paramset import ParamSet

_BUILDERS: dict[str, Callable[[ParamSet], Controller]] = {
    "direct": DirectController,
}


def create_controller(params: ParamSet) -> Controller:
    """Build the controller chosen in the parameters."""
    return _BUILDERS[params.choice("control.controller_type")](params)
