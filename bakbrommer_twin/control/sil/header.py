"""Generates the C header that mirrors ``control/interface.py``.

Run ``python -m bakbrommer_twin.control.sil.header`` after changing
``ControllerInputs`` or ``ControllerOutputs``; it rewrites ``bb_controller.h``.
A test fails when the committed header is out of date.
"""

from __future__ import annotations

import inspect
from dataclasses import fields
from pathlib import Path

from bakbrommer_twin.control import interface
from bakbrommer_twin.control.interface import ControllerInputs, ControllerOutputs

HEADER_PATH = Path(__file__).parent / "bb_controller.h"


def _comments(cls: type) -> dict[str, str]:
    """Field name → the comment written behind it in the Python source."""
    found = {}
    for line in inspect.getsource(cls).splitlines():
        if ":" in line and "#" in line:
            name = line.split(":")[0].strip()
            found[name] = line.split("#", 1)[1].strip()
    return found


def _struct(cls: type, name: str) -> str:
    comments = _comments(cls)
    lines = ["typedef struct {"]
    for item in fields(cls):
        lines.append(f"    double {item.name};  /* {comments.get(item.name, '')} */")
    lines.append(f"}} {name};")
    return "\n".join(lines)


def header_text() -> str:
    """The complete text of ``bb_controller.h``."""
    return f"""/* GENERATED FILE - do not edit.
 * Made from {Path(interface.__file__).name} by: python -m bakbrommer_twin.control.sil.header
 *
 * Interface between the simulated vehicle and controller code written in C.
 * All values are doubles in SI units (see the comment behind each field).
 */
#ifndef BB_CONTROLLER_H
#define BB_CONTROLLER_H

#ifdef _WIN32
#define BB_API __declspec(dllexport)
#else
#define BB_API
#endif

/* What the controller reads every control period. */
{_struct(ControllerInputs, "bb_inputs_t")}

/* What the controller writes every control period. */
{_struct(ControllerOutputs, "bb_outputs_t")}

/* Functions a controller library must provide: */

/* Number of tuning parameters the controller wants from the simulator. */
BB_API int bb_param_count(void);
/* Dotted registry name of parameter `index`, e.g. "control.limits.battery_current". */
BB_API const char *bb_param_name(int index);
/* Called once per parameter before the run; `value` is in SI units. */
BB_API void bb_set_param(int index, double value);
/* Return to the power-on state. */
BB_API void bb_reset(void);
/* One control period: read `in`, fill `out`. */
BB_API void bb_step(const bb_inputs_t *in, bb_outputs_t *out);

#endif /* BB_CONTROLLER_H */
"""


def main() -> None:
    """Rewrite the committed header."""
    HEADER_PATH.write_text(header_text(), encoding="utf-8")
    print(f"Wrote {HEADER_PATH}")


if __name__ == "__main__":
    main()
