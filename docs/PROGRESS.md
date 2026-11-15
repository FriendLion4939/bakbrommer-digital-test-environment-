# Progress log

One status note per phase, newest at the bottom.

## Phase 1 — parameter registry, profiles, skeleton, tests, Docker ✅

**Done**
* Parameter registry (`params/`): numbers, integers, switches, choices and
  curves; friendly-unit definitions converted to SI once; ranges validated;
  status flag per value (`measured / estimated / default / calibrated`).
* Profiles as YAML with a `base` profile, saved differences only, automatic
  history copies, compare, copy, delete.
* First parameter categories: geometry and mass (five mass components).
* Mass properties (`physics/mass.py`): total mass, centre of gravity,
  inertia, static wheel loads, rigid-vehicle wheel-lift limit and tip-over
  angle; shown as calculated values.
* Web UI skeleton with the auto-generated parameter editor (edit, save,
  save-as, undo, delete, compare, history, calculated values).
* Translation file (`ui/translations/en.yaml`), command line tool,
  `start.sh` / `start.bat`, `Dockerfile` + `docker-compose.yml`.
* Docs: PLAN, ARCHITECTURE, HOW_TO_CHANGE, CLAUDE.md (grown each phase).
* Tests: units, registry, parameter sets, profiles, mass properties, UI
  smoke tests, and project-rule guards (file length, docstrings, unused
  parameters, translation keys).

**Checked**
* `scripts/check.sh` (ruff, mypy --strict, pytest): all pass.
* Web UI opened in a real browser: edit → calculated values update → save.
* Docker: image built and started in the build sandbox; all tests pass
  inside the container and the UI answers. One caveat: the sandbox blocks
  Debian's package servers, so the `apt-get install gcc` line of the
  Dockerfile could not be executed there (it was skipped for the check).
  gcc is only needed for the software-in-the-loop example of Phase 6.

**Notes**
* Parameters for motors, engine, battery etc. are added in the phase that
  implements the model using them, so that "every parameter is used" always
  holds.
