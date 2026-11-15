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
