# Instructions for AI maintainers

This project is maintained by AI models on behalf of a vehicle builder who
does not program. Keep it simple, tested and documented. Read
`docs/ARCHITECTURE.md` first; use the recipes in `docs/HOW_TO_CHANGE.md`.

## Commands

```bash
source .venv/bin/activate          # once per shell (create with ./start.sh or: python3.12 -m venv .venv && pip install -e ".[dev]")
python -m pytest                   # all tests (one command)
python -m pytest tests/test_mass.py -k cargo   # a subset
scripts/check.sh                   # ruff + mypy + all tests (about 3 minutes) — run before every commit
bakbrommer-twin ui                 # start the web interface on port 8501
bakbrommer-twin run slalom         # run a scenario in the terminal
python scripts/update_reference.py     # after an INTENDED behaviour change: refresh tests/reference, then review the diff
python scripts/make_example_logs.py    # regenerate the synthetic example logs (after changing the example CAN layout or sensors)
python -m bakbrommer_twin.control.sil.header   # after changing control/interface.py: regenerate the C header
python scripts/performance_check.py    # 10-minute ride timing (must stay well under a minute)
```

## Where to look

| Question | File |
|---|---|
| What is where, and what calls what? | `docs/ARCHITECTURE.md` |
| How do I add a parameter / sensor / scenario / ride mode / chart / log format? | `docs/HOW_TO_CHANGE.md` |
| Which equation is used and why? | `docs/PHYSICS.md` |
| What does the controller do? How does C code plug in? | `docs/CONTROLLER.md`, `docs/SIL.md` |
| How do import, replay and calibration work? | `docs/DATA_IMPORT.md` |
| What was checked, what is known to be limited? | `docs/PROGRESS.md` |

## Rules

1. **Never hard-code a parameter.** Every physical, electrical, control,
   sensor, driver or numerical value is declared once in
   `bakbrommer_twin/params/definitions/` and read through a `ParamSet`
   (`params.num("battery.capacity")`). Physical constants (gravity, π) and
   pure maths (0.5 in ½·m·v²) are the only literals allowed in formulas.
2. **Every change comes with a test.** New behaviour → new test. Bug fix →
   a test that fails without the fix.
3. **Update the docs when behaviour changes**: `docs/ARCHITECTURE.md` (module
   map / data flow), `docs/HOW_TO_CHANGE.md` (recipes), `docs/PHYSICS.md`
   (equations), `README.md` (what the user sees).
4. **SI units inside.** Convert only at the edges: parameter definitions,
   YAML files, UI, log import/export. Use `params/units.py`.
5. **Every physics equation has a comment** with its source or derivation
   and the units.
6. **Files stay under about 400 lines**; one responsibility per file. A test
   enforces the limit. Split a file before it grows past it.
7. **Type hints everywhere** (`mypy --strict` passes), a docstring on every
   module and public function/class, no dead code, no TODO stubs.
8. **All UI text goes through `t("key")`** with the text in
   `translations/en.yaml`.
9. **Never present made-up data as real.** Example logs are synthetic and
   say so. Results stay labelled "not validated" until a profile has been
   calibrated against real ride data.
10. **Small steps.** One recipe at a time, run `scripts/check.sh`, commit.
11. **Check the UI in a real browser** after changing a page. The headless
    page tests (`tests/test_ui_smoke.py`) cannot see everything (a folder
    named `pages` once broke navigation without failing a test).
12. **If a regression number changes** (`tests/test_scenario_regression.py`),
    first understand why. Only then refresh the reference file.

## Conventions

* Wheel order everywhere: index 0 = front-left, 1 = front-right, 2 = rear.
* Body axes: x forward, y left, z up. Positive steering/yaw = left turn.
* Parameter names: `category.name` or `category.group.name`, lower-case with
  underscores. Definitions give values in a friendly unit; code sees SI.
* Per-step physics code uses plain Python floats and attributes (no NumPy,
  no object creation inside the step) — this is what makes the simulator
  fast enough.
* Tests live in `tests/test_<module>.py`. Shared fixtures in `tests/conftest.py`,
  helpers (test rig, cached library runs) in `tests/helpers.py`.
* Guard tests keep the rules: `test_project_rules.py` (file length,
  docstrings, translation keys), `test_param_usage.py` (no unused parameter),
  `test_docs.py` (docs name only things that exist; every module is in
  ARCHITECTURE.md), `test_performance.py` (speed; no NumPy numbers in the loop).
* The UI folder for pages is `ui/views/` — never rename it to `pages`
  (Streamlit would hijack it).
* Friction (brakes, clutch, rolling resistance) is solved as a constraint, not
  as a force with a sign function — see `docs/PHYSICS.md` §5 before touching it.

## What to tell the user

The user needs plain language. When you change something, say what it does
for the vehicle model, how to see it in the UI, and whether any value still
needs measuring.
