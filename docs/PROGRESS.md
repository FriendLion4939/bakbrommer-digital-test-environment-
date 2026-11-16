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

## Phase 2 — longitudinal dynamics ✅

**Done**
* Physics subsystems, one file each: tyres (magic formula, combined slip,
  relaxation), wheels (spin + friction as a constraint), chassis (6-DOF rigid
  body on three push-only spring wheels), electric drives (torque limits,
  loss model, regen, thermal derating), battery (Thevenin, SoC, heat, BMS
  trip), petrol engine (torque curve, idle, rev limit, starter, fuel),
  gearbox (manual / CVT, centrifugal clutch with true lock-up), hydraulic
  brakes, aerodynamics with wind, gradient, energy ledger.
* 319 parameters so far, all editable in the UI.
* Controller boundary (`ControllerInputs` / `ControllerOutputs`) and the
  simple `direct` controller; complete sensor suite (19 sensors with noise,
  bias, resolution, rate, delay) — built now because the controller boundary
  needs it; the hybrid "brain" itself is Phase 4.
* Scenario files, route builder, driver model (speed plan, pedals, gears,
  steering), simulation loop, recorder (about 100 channels), safety monitor,
  summary and scenario metrics, results saved to disk, CLI `run`.
* Scenarios: 0–50 km/h, top speed, hill climbs 5/10/15 %, hill descent 10 %,
  emergency braking dry and wet.
* Derived values: power, gear speeds, top speed estimate, power-to-weight.
* `docs/PHYSICS.md` with all equations.

**Checked**
* 191 tests pass (`scripts/check.sh`: ruff, mypy --strict, pytest).
* Static wheel loads equal the hand calculation; coast-down deceleration
  matches the hand calculation within 1 %; a parked vehicle on a 15 % slope
  moves less than 0.1 mm in 10 s; load transfer under acceleration matches
  `m·a·h/L`.
* Mechanical energy balance closes within 0.02 % in every scenario
  (1–1.5 % in the two emergency stops with locked, sliding wheels).
  Momentum change equals the impulse of the forces.
* Simulated top speed (63.5 km/h) agrees with the independent power-balance
  estimate (65.9 km/h).
* Speed: about 44 µs per 1 ms step → a 10-minute ride takes about 26 s.

**Example results with the default (estimated!) parameters**
| Scenario | Result |
|---|---|
| 0–50 km/h | 7.7 s |
| Top speed | 63.5 km/h |
| Hill climb 5 / 10 / 15 % | holds 60 / 54 / 41 km/h |
| Emergency stop from 50 km/h, dry / wet | 10.9 m / 16.0 m (front wheels lock at full lever — reported) |

**Notes and findings**
* The two motor controllers together must stay below the BMS limit. The
  default line-current limit is therefore 16 A per controller (BMS 35 A).
  With the earlier 60 A the simulated BMS tripped two seconds into a
  full-throttle start — as the real one would.
* Whether the petrol throttle is a cable or a servo is unknown; it is the
  parameter `engine.throttle_by_wire` (default: cable).
* Reverse driving is not modelled.
