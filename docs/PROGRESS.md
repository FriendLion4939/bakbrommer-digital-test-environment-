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
* Translation file (`translations/en.yaml`), command line tool,
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

## Phase 3 — lateral and three-wheeler dynamics ✅

**Done**
* Cornering uses the Phase 2 chassis and tyre model unchanged: load transfer,
  wheel lift and rollover come out of the push-only wheel springs.
* Steering geometry: centre-pivot (wheels move with the axle) and Ackermann
  (percentage adjustable); tilting documented as an extension point.
* Road model: surface per wheel (split friction), seeded bumps per surface,
  gradient, wind. New parameter `environment.default_surface`.
* Rider: pure-pursuit path following, and a **wheel-lift reaction** (steer
  out, close throttle, light brake, gentle cornering until recovered).
  Without it a three-wheeler on two wheels rolls over within a second —
  the simulator shows this when the reaction gain is set to 0.
* Safety report: wheel lift (with height), spin, lock, sideways slide,
  rollover margin, tip-over point, rollover (stops the run).
* Route segment types: slalom, lane change, free waypoints.
* Scenarios: steady-state circle (finds the lift speed), slalom, roundabout,
  lane change with full cargo, split-friction acceleration.
* Profile "Wet weather".

**Checked**
* 232 tests pass.
* Steady circle: yaw rate = v/R within 3 %, lateral acceleration = v²/R
  within 6 %, left/right mirror exactly.
* Front load difference in a corner equals `m·a_y·h/(t/2)` within 8 % (a
  single rear wheel carries no roll moment).
* Wheel lift in the circle test at 0.27 g / 19.7 km/h on a 12 m radius; the
  independent rigid-body formula gives 0.285 g. Higher cargo lifts sooner,
  wider track later.
* Bump height statistics match the surface parameter; same seed → identical
  run.

**Findings worth knowing (with the estimated default geometry!)**
* The wheel-lift limit is low: about 0.28 g. The centre of gravity is 0.59 m
  high and only 40 % of the weight is on the 0.85 m wide front axle. Cargo in
  the box *improves* this (0.40 g with 80 kg low in the box) because it moves
  the centre of gravity forward. Measure CoG height and position — these
  numbers decide everything about wheel lift.
* The default rider therefore plans corners at 2.0 m/s² (0.2 g). Sporty
  settings (3.5 m/s²) give repeated 20–40 mm wheel lifts but no rollover.
* With both motors given the same torque (the simple `direct` controller),
  the unloaded inner wheel spins up in hard cornering and on split friction.
  Traction control and torque vectoring in Phase 4 address this.

**Limits**
* The rider model does not lean. Camber thrust and gyroscopic effects are not
  modelled (see `docs/PHYSICS.md`, "Known simplifications").

## Phase 4 — controller, ride modes, sensors ✅

**Done**
* Reference controller (`control/reference/`), one small file per block:
  speed estimate, ride modes with gliding mode changes, petrol engine
  start/stop, torque blending, regen (coast + brake), rollover protection,
  torque vectoring, traction control and regen anti-lock, battery current /
  low-voltage / temperature limits, torque rate limit. 91 tuning parameters,
  all in the UI. Described in `docs/CONTROLLER.md`.
* It is now the default controller; `direct` remains for physics tests.
* Sensors with noise, bias, resolution, rate and delay feed the controller
  (built in Phase 2, now exercised by the brain).
* Rider model reworked: acceleration-based speed control that knows the real
  brake strength, planned halts (`stop_s`), anti-windup, cornering no harder
  than its limit plus a correction margin, balance reaction on wheel lift.
* Vertical damping now acts on body motion only (a damper fed with road
  height rate, without a wheel mass in between, exaggerated every bump).
* New scenarios: rough-terrain race lap, city stop-and-go, energy/range
  cycle, electric sprint then back to hybrid. New profile "Future battery
  (150 A BMS)".

**Checked**
* 272 tests pass, including one test per controller block and closed-loop
  tests: battery current held at the limit (35 A and 150 A setups), no BMS
  trips, wheel spin on split friction removed without losing drive, outer
  wheel favoured in corners, torque cut near the wheel-lift limit, energy
  recovered downhill without over-charging, modes ranked eco < normal ≤
  sport, eco launches electrically then starts the engine, standalone keeps
  the engine off and hybrid brings it back, no torque jerk on a mode change,
  realistic sensors change the 0–30 km/h time by less than 5 %.

**Example results (estimated parameters!)**
| Scenario | Result |
|---|---|
| 0–50 km/h, Normal mode | 8.2 s, battery current ≤ 30 A |
| 0–30 km/h, Standalone electric, 35 A BMS / 150 A BMS | 7.2 s / 3.8 s |
| Top speed, Normal mode | 60 km/h (electric assist has faded out) |
| City stop-and-go (538 m, 4 stops) | 96 s |
| Range cycle (2.9 km) | 27 Wh/km and 1.8 L/100 km → about 79 km on the battery, 228 km on the tank |
| Rough race lap, Sport | 52 s, 31 wheel lifts (bumps and corners), no rollover |

**Open questions for the builder** (each is a parameter with a default)
* Is the petrol throttle a cable or a servo? (`engine.throttle_by_wire`)
* Can the controller start and stop the petrol engine?
  (`control.engine_auto_start_stop`)
* Do the Fardrivers accept a torque command over CAN, and how fast do they
  follow it? (`motor.torque_response_time`)

## Phase 5 — web interface, batch tools, reports ✅

**Done**
* Web interface with six pages: Start, Parameters, Scenarios (library,
  editor with segment table, live route/speed-plan preview, click-to-draw
  routes), Run a simulation, Results and comparison, Sweeps and optimiser.
* Results view: headline numbers, safety report, stacked charts on one
  shared time or distance axis (zoom one, all follow), any recorded signal
  can be added, top-down 2D animation (wheel colour = load, red hollow wheel
  = lifted, orange outline = slipping, arrows = tyre forces), route map,
  export to CSV / printable HTML / PDF.
* Run comparison: tick two to four saved runs → metric table with
  differences (rows that differ by more than 5 % highlighted), differing
  parameters, overlaid charts (colour = signal, line style = run).
* Batch tools (parallel worker processes): one- and two-parameter sweeps,
  Monte Carlo with statistics and share of unsafe samples, optimiser
  (differential evolution) under hard safety constraints with an "apply to
  profile" button.
* All texts in `translations/en.yaml`; parameter forms generated from the
  registry.

**Checked**
* 299 tests pass, including a smoke test per page and tests for charts,
  tables, exports, sweeps, Monte Carlo and the optimiser.
* Every page opened in a real browser (Chromium): edit a parameter, run a
  scenario, view charts, compare runs, run a sweep with parallel workers.
  This found and fixed one bug the headless tests cannot see (a folder named
  `pages` made Streamlit bypass the navigation; it is now `views`).
* The optimiser test recovers a known optimum: the largest motor torque that
  keeps the battery current under a given limit.

**Limits**
* The animation shows at most 240 frames per run (long runs are thinned).
* The comparison overlays at most four runs.
* The PDF report has static charts; the HTML report is interactive and can
  be printed from the browser.

## Phase 6 — real data import, replay, calibration, software-in-the-loop ✅

**Done**
* Import of CSV logs with a column-mapping wizard (guessed from column names,
  editable, saved for next time), candump logs and SavvyCAN CSV decoded with
  an editable DBC-style YAML definition file, and conversion of `.dbc` files.
* Cleaning: plausible-range check, resampling, gap detection (gaps stay
  empty), optional zero-phase low-pass filter, time alignment of two logs,
  quality table.
* Replay of a recorded ride (throttle, brake, steering, ride mode; gear
  inferred from engine and wheel speed) with simulated-vs-measured overlays
  and fit quality (RMSE, bias, R²).
* "What if": replay the same ride with changed settings and compare.
* Calibration by least squares with before/after quality; accepted values are
  marked `calibrated`; the profile becomes "validated" only for real data.
* Software-in-the-loop: C header generated from the Python interface, a
  working example controller in C, automatic compile and load
  (`control.controller_type = sil`). Described in `docs/SIL.md`.
* Pages "Import and replay a ride" and "Calibration".

**Checked**
* 333 tests pass.
* The same simulated ride written as CSV, candump and SavvyCAN decodes to the
  same signals; bit layouts follow the DBC convention (Intel and Motorola).
* Calibration on the synthetic example recovers all four hidden values within
  1 % (mass 150.6 / 150 kg, rolling resistance 1.304 / 1.3, frontal area
  1.154 / 1.15 m², battery resistance 85.1 / 85 mΩ) in 30 simulations (53 s).
* The C example controller compiles with gcc and drives the simulated vehicle
  (0–50 km/h in 7.9 s, no BMS trip).
* Import page exercised in a real browser.

**Important: no real data yet**
* The example logs are **synthetic** (generated by the simulator, labelled as
  such in the files, the README and the UI). The CAN layout is an example.
  Nothing in this repository has been validated against the real vehicle.

**Lessons the replay taught (now handled and documented)**
* Logs do not contain the gear; a replay that guesses it wrongly drifts off.
  It is now inferred from engine speed ÷ wheel speed.
* Brake pressure sensor noise, replayed as tiny brake applications, biased the
  rolling-resistance fit by about 10 %. Readings below the brake threshold are
  now ignored.
* Open-loop steering replay with wrong parameters can roll the simulated
  vehicle over in a corner the real one took; the example ride is therefore a
  calm one, and the docs explain what this means.

**Limits**
* A replay assumes level ground; gradients in a real ride will show up as
  speed/current mismatch.
* Calibration runs its simulations one after another (about 1.5 s per 80 s of
  ride each).
* SIL needs a C compiler on the machine (present in the Docker image).
