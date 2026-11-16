# Software-in-the-loop (SIL): running controller C code in the simulator

The simulator can run controller code written in C — compiled for the PC, not
for the STM32 — in place of the Python reference controller. The vehicle,
sensors, scenarios, charts and safety report stay exactly the same, so the C
code is tested against the same rides.

## Try the shipped example

1. A C compiler must be installed (`gcc` on Linux — the Docker image has it;
   MinGW-w64 on Windows).
2. In the UI: Parameters → Controller → set **Controller** to `sil`.
3. Run any scenario. The result page shows `sil` as the controller.

The example (`bakbrommer_twin/control/sil/example_controller.c`) is a small
hybrid logic: throttle → motor torque, battery current limit, regen on the
brake, torque rate limit. It is compiled automatically on first use and cached.

## The interface — `bb_controller.h`

Generated from `control/interface.py` (never edit it by hand; regenerate with
`python -m bakbrommer_twin.control.sil.header`). It contains:

* `bb_inputs_t` — every sensor reading the controller gets (doubles, SI units).
* `bb_outputs_t` — torque commands, engine commands, diagnostics.
* Five functions a controller library must provide:

| Function | Purpose |
|---|---|
| `int bb_param_count(void)` | How many tuning values the controller wants. |
| `const char *bb_param_name(int i)` | The registry name of value `i`, e.g. `"control.limits.battery_current"`. |
| `void bb_set_param(int i, double value)` | Called once per value before a run (SI units). |
| `void bb_reset(void)` | Back to the power-on state. |
| `void bb_step(const bb_inputs_t *in, bb_outputs_t *out)` | One control period. |

Parameters are passed **by name**: the C code lists the registry parameters it
needs and the simulator sends their current values. Tuning a value in the UI
therefore reaches the C code without recompiling.

## Plugging in the real STM32G4 control code

1. Separate the firmware's control function from the hardware layer: it should
   take sensor values and return commands, with no register access inside
   (the hardware reads/writes stay in the STM32 project).
2. Write a thin wrapper C file that includes `bb_controller.h`, implements
   the five functions, converts `bb_inputs_t` into the firmware's own
   structures (and units!), calls the control function, and copies the
   results into `bb_outputs_t`. Start by copying `example_controller.c`.
3. Tell the simulator to use it: set the environment variable
   `BAKBROMMER_SIL_SOURCE` to the path of the wrapper file (in
   `docker-compose.yml` under `environment:`, or before starting `start.sh`).
   If the firmware consists of several C files, `#include` them from the
   wrapper or extend `build()` in `control/sil/build.py` to pass them all to
   the compiler.
4. Select the `sil` controller and run the scenarios. Compare with the
   `reference` controller on the Results page.

Things to watch:

* **Units.** The interface is SI (rad/s, Pa, m/s). Convert in the wrapper.
* **Fixed-point or `float` firmware** works unchanged; only the wrapper uses
  `double`.
* **Timing.** `bb_step` is called once per control period (`control.loop_rate`),
  with the period in `in->dt`. Code that assumes a fixed period should check it.
* **State.** All state must be reset by `bb_reset` — a simulation may be
  repeated many times in one process (sweeps, optimiser).

## Limits

* One controller instance per process (the C code keeps global state). Batch
  tools start separate worker processes, which is safe.
* The STM32F7 (display/logging) and the CAN link between the two boards are
  not simulated; the interface represents what the G4 control function sees.
