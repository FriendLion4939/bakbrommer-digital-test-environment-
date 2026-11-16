"""Loads a compiled controller library and presents it as a :class:`Controller`.

The two interface records are copied to and from C structs of doubles each
control period. Parameters are handed over by name: the library says which
registry parameters it wants (``bb_param_name``), the bridge sends their SI
values (``bb_set_param``). So C code and simulator always use the same
numbers.
"""

from __future__ import annotations

import ctypes
import os
from dataclasses import fields
from operator import attrgetter
from pathlib import Path

from bakbrommer_twin.control.interface import ControllerInputs, ControllerOutputs
from bakbrommer_twin.control.sil.build import EXAMPLE_SOURCE, build
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.types import Kind

ENV_SOURCE = "BAKBROMMER_SIL_SOURCE"  # path of the C file to use instead of the example
_INPUT_NAMES = tuple(item.name for item in fields(ControllerInputs))
_OUTPUT_NAMES = tuple(item.name for item in fields(ControllerOutputs))


def sil_source() -> Path:
    """The C file that is compiled: the example, unless the environment names another."""
    chosen = os.environ.get(ENV_SOURCE)
    return Path(chosen) if chosen else EXAMPLE_SOURCE


class SilController:
    """A controller whose logic runs in compiled C code."""

    def __init__(self, params: ParamSet, source: Path | None = None) -> None:
        self.library_path = build(source or sil_source())
        self._library = ctypes.CDLL(str(self.library_path))
        self._inputs = (ctypes.c_double * len(_INPUT_NAMES))()
        self._outputs = (ctypes.c_double * len(_OUTPUT_NAMES))()
        self._read_inputs = attrgetter(*_INPUT_NAMES)
        library = self._library
        library.bb_param_count.restype = ctypes.c_int
        library.bb_param_name.restype = ctypes.c_char_p
        library.bb_param_name.argtypes = [ctypes.c_int]
        library.bb_set_param.argtypes = [ctypes.c_int, ctypes.c_double]
        library.bb_step.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.param_names: list[str] = []
        for index in range(library.bb_param_count()):
            name = library.bb_param_name(index).decode("utf-8")
            self.param_names.append(name)
            kind = params.registry.get(name).kind
            if kind is Kind.NUMBER:
                value = params.num(name)
            elif kind is Kind.INTEGER:
                value = float(params.integer(name))
            elif kind is Kind.FLAG:
                value = 1.0 if params.flag(name) else 0.0
            else:
                raise ValueError(f"The C controller asks for '{name}', which is not a number")
            library.bb_set_param(index, value)
        library.bb_reset()

    def reset(self) -> None:
        """Return the C code to its power-on state."""
        self._library.bb_reset()

    def step(self, inputs: ControllerInputs, outputs: ControllerOutputs) -> None:
        """Copy the inputs into C, run one control period, copy the outputs back."""
        self._inputs[:] = list(self._read_inputs(inputs))
        self._library.bb_step(self._inputs, self._outputs)
        for name, value in zip(_OUTPUT_NAMES, self._outputs, strict=True):
            setattr(outputs, name, value)
