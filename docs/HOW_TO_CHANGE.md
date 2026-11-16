# How to change things — recipes

Each recipe lists every file to touch. After any change run
`scripts/check.sh` (style, types, all tests).

## Add a parameter

1. Open the file for its category in `bakbrommer_twin/params/definitions/`.
2. Add one call inside `register()`, giving the value in a friendly unit:
   ```python
   reg.number("geometry.seat_height", 0.80, "m", 0.3, 1.5, "Seat height",
              "Height of the seat above the ground.", Status.ESTIMATED)
   ```
   Other kinds: `reg.integer`, `reg.flag`, `reg.choice`, `reg.curve`.
3. Read it where it is needed, in a constructor, never inside the step loop:
   `self.seat_height = params.num("geometry.seat_height")`.
4. It appears in the UI automatically. `tests/test_param_usage.py` fails if
   nothing reads the new parameter — that is intended.
5. Need a unit that is missing? Add one line to `UNITS` in `params/units.py`.

## Add a parameter category (a new tab in the UI)

1. Create `params/definitions/<category>.py` with a `register(reg)` function
   that starts with `reg.category("<category>", "Title")`.
2. Add the module to `_MODULES` in `params/definitions/__init__.py`.

## Add a calculated (derived) value

1. Put the formula in the physics module it belongs to (with a comment
   giving the derivation and units).
2. Add a `DerivedValue(...)` line in `params/derived.py`.
3. Add a test with a hand-calculated case.

## Add a profile

Use the UI (Parameters → "Save as new profile"), or copy a file in
`data/profiles/` and edit it. Only values that differ from the `base`
profile need to be listed.

## Change or add a UI text / add a language

Texts are in `bakbrommer_twin/ui/translations/en.yaml`. For Dutch, copy the
file to `nl.yaml` and translate the values; the language picker finds it.

## Add a UI page

1. Create `ui/pages/<name>.py` with a `render()` function.
2. Add `nav.<name>` to `en.yaml` and one line to `PAGES` in `ui/app.py`.
3. Add a smoke test in `tests/test_ui_smoke.py` using `_page("<name>")`.

## Add a scenario

Use the UI scenario editor, or add a YAML file to `data/scenarios/`. Fields
are documented in `bakbrommer_twin/scenarios/scenario.py`; copy an existing
file as a start. Then run `python scripts/update_reference.py` so the
regression test knows the new scenario, and check the new numbers in
`tests/reference/scenarios.yaml` make sense.

## Add a scenario metric type

1. Write a function in `scenarios/metrics.py` taking `(data, events, spec)`
   and returning a `Metric`; add it to `_METRICS`.
2. Use it in a scenario file: `metrics: [{type: my_metric}]`.
3. Add a test in `tests/test_simulator.py`.

## Add a road surface

Add one line to `_SURFACE_DEFAULTS` in `params/definitions/wheels.py`
(friction, sliding/peak ratio, peak-slip scale, rolling resistance, bump
height in mm, bump wavelength in m). It appears in the parameter editor and
can be used in scenarios by name.

## Change a tyre, motor or engine curve

* Tyre force curve shape: parameters under "Tyres" and "Road surfaces"; the
  formula is in `physics/tyres.py` and `physics/surfaces.py`.
* Engine torque curve: the two lists `engine.torque_curve_speed` /
  `engine.torque_curve_torque` (same length) in the parameter editor.
* Motor torque limits and losses: parameters under "Electric motors"; formulas
  in `physics/motors.py`. To replace the loss model by a measured efficiency
  map, change `ElectricDrive.step` (bus power) and `ElectricDrive.efficiency`
  together and extend `tests/test_motors.py`.

## Add a sensor

1. `params/definitions/sensors.py`: add a `SensorSpec` line to `SENSOR_SPECS`.
2. `sensors/suite.py`: add the true value to `_getters`.
3. If the controller needs it: add a field to `ControllerInputs`
   (`control/interface.py`) and copy it in `SensorSuite.fill`.
4. Add a test in `tests/test_sensors.py`.
The five sensor settings and the `sens_<name>` chart channel appear
automatically.

## Add a ride mode

1. `params/definitions/control.py`: append the name to `RIDE_MODES`.
2. `params/definitions/control_reference.py`: add one value per row of
   `_MODE_NUMBERS` and one entry in `_MODE_ENGINE`.
3. Nothing else: `ModeManager` reads all modes from the parameters, the mode
   switch accepts the new index, scenarios accept the new name.
4. Add a line to the table in `docs/CONTROLLER.md` and a test in
   `tests/test_controller_closed_loop.py`.

## Change the control logic

Each block is one small file in `control/reference/`; `controller.py` shows
the order. Add tuning values as parameters under `control.*`
(`params/definitions/control_reference.py`). Test the block alone in
`tests/test_controller_blocks.py` and in the loop in
`tests/test_controller_closed_loop.py`.

## Add a recorded channel (signal)

Append a `ChannelDef` with its getter in `sim/channels.py`. It is recorded,
exported and selectable in the charts.

## Add a safety check

Append a `_Check(...)` in `SafetyMonitor.__init__` (`sim/safety.py`) and add
the text `event.<kind>` to `ui/translations/en.yaml`.
