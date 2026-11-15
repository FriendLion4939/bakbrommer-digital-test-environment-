# Bakbrommer Twin — architecture plan

Written before any code. It records the decisions the rest of the project follows.
If a decision changes later, update this file and `docs/ARCHITECTURE.md`.

## 1. Goals, in priority order

1. **Correct enough for engineering decisions** — especially load transfer,
   front-wheel lift and rollover on a three-wheeler.
2. **Maintainable by another AI model in small steps** — small files, one
   responsibility per file, no hidden numbers, recipes for common changes.
3. **Usable by a non-programmer** — one command to start, everything through
   the browser.
4. **Fast enough** — a 10-minute ride at a 1 ms step in well under a minute.

## 2. Technology decisions

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.12 | As requested. |
| Physics maths | Plain Python floats in the per-step loop, NumPy/SciPy outside it | NumPy scalar maths is slower than plain floats for a 3-wheel model; NumPy/SciPy are used for results, import, fitting and optimisation. No JIT compiler (Numba/C) so the code stays easy to read and change. |
| Parameter registry | Pydantic models | Validates every definition, profile and scenario file. |
| Files | YAML for profiles, scenarios, CAN definitions, column mappings, translations | Human-readable and diff-able. |
| UI | Streamlit (multi-page) + Plotly | Far less code than FastAPI + a hand-written frontend; forms, tables, file upload and charts are built in. Works on a phone browser. |
| PDF report | Matplotlib `PdfPages` | Pure Python, works offline, no browser engine needed. HTML report uses Plotly. |
| Tests | pytest (+ ruff and mypy in `scripts/check.sh`) | One command. |
| Delivery | Docker Compose, `start.sh`, `start.bat` | As requested. |

## 3. Package layout

```
bakbrommer_twin/
  params/        parameter registry, units, profiles, derived values
    definitions/ one file per category — the ONLY place parameters are declared
  physics/       one file per subsystem (tyres, motors, engine, gearbox, battery,
                 brakes, chassis, steering, aero, surfaces, mass, thermal, vehicle)
  sensors/       generic sensor model (noise, bias, delay, resolution) + sensor suite
  control/       controller interface, direct controller, reference controller
                 (reference/ = readable Python version of the STM32G4 logic),
                 sil/ = software-in-the-loop bridge to C code
  scenarios/     route geometry, scenario files, driver model, metrics
  sim/           simulation loop, recorder/channels, safety monitor, energy audit,
                 run results on disk
  batch/         parallel runner, sweeps, Monte Carlo, optimiser
  data_import/   CSV logs, CAN logs, CAN message definitions, column mapping,
                 cleaning, replay
  calibration/   parameter fitting against real logs
  reports/       summary metrics, safety report, figures, HTML/PDF/CSV export
  ui/            Streamlit app, pages, translations
data/            profiles, scenarios, CAN definitions, mappings, example logs
runs/            saved simulation results (created at run time)
tests/           pytest suite
docs/            PLAN, ARCHITECTURE, HOW_TO_CHANGE, PHYSICS, PROGRESS
```

Rule: no source file longer than about 400 lines (a test enforces it).

## 4. Parameters

* Every number that describes the vehicle, the environment, the controller,
  the sensors, the driver or the numerical method is declared once in
  `params/definitions/*.py` with name, default, unit, range, description,
  category and status (`measured` / `estimated` / `default`, plus
  `calibrated` once fitted to a log).
* Names are dotted: `battery.internal_resistance`. The first part is the
  category (a tab in the UI), the second optional part a group.
* Definitions are written in a friendly unit (`rpm`, `km/h`, `deg`, `Ah`).
  The registry converts to SI once; all code sees SI. Conversion back happens
  only in the UI, in YAML files and in import/export.
* Value kinds: number, integer, yes/no, choice, curve (list of numbers).
* A `ParamSet` holds one complete set of values. Physics classes read what
  they need in their constructor; the per-step code uses plain attributes.
* A **profile** is a YAML file with a `base` profile and only the values that
  differ. Saving a profile also stores a time-stamped copy (history).
* Tests guarantee: every parameter is used somewhere, every parameter name
  used in code exists, and no file reads a parameter that is not declared.
* The UI editor is generated from the registry. Adding a parameter makes it
  appear in the UI with no UI change.

## 5. Physics model

Details and equations are in `docs/PHYSICS.md` (written with the code).

* **Chassis: one rigid body with six degrees of freedom** (position, yaw,
  pitch, roll) standing on three wheels. Each wheel is a vertical
  spring-damper that can only push, never pull. Consequences:
  * load transfer in roll and pitch needs no special formula — it follows
    from the body's motion;
  * a wheel "lifts" when its spring is fully extended — the load becomes
    zero and the gap to the ground is known;
  * rollover is simply the roll angle growing past the tipping point;
  * rough ground is a height profile under each wheel.
* **Road frame**: the road surface is the reference plane; gradient is
  modelled by tilting gravity. Elevation is tracked for the energy audit.
* **Mass properties** are computed from components (chassis, battery, rider,
  cargo, fuel), so the centre of gravity moves with the cargo.
* **Tyres**: simplified magic formula `F = D·sin(C·atan(B·x))` with combined
  slip (friction ellipse), load sensitivity and relaxation length. Surfaces
  are described by peak friction, sliding/peak ratio, slip at peak, rolling
  resistance and roughness, per wheel.
* **Wheels**: each has its own spin speed. Brake and rolling friction are
  solved as true stick/slip friction (a held wheel stays exactly still).
* **Electric motors**: torque limited by phase current, voltage (back-EMF)
  and controller line current; loss model (copper, iron, controller) from
  which the efficiency map is derived; regeneration; one-node thermal model
  with derating.
* **Petrol engine**: full-throttle torque curve, friction, Willans-line fuel
  model (gives the fuel map), idle governor, rev limiter, starter, on/off.
* **Gearbox/clutch**: manual N-speed with centrifugal clutch, or CVT. The
  clutch is solved as stick/slip friction between engine and rear wheel.
* **Battery**: open-circuit voltage curve, series resistance plus one RC
  pair (sag), state of charge, temperature, BMS current limit and trip.
* **Brakes**: hydraulic pressure → caliper torque per wheel, front/rear
  circuits, lock detection.
* **Aerodynamics**: drag from frontal area × Cd (cargo box shape options),
  side force, wind.
* **Integration**: fixed step (default 1 ms), semi-implicit Euler
  (velocities first, then positions). Stable at the default step; tests
  check energy balance and momentum.

Known simplifications (documented in `docs/PHYSICS.md`): no camber thrust,
no wheel gyroscopic moment, no tyre enveloping of bumps, no suspension
kinematics, centre-pivot steering moves the wheels but not the cargo mass.

## 6. Controller ("brain") boundary

```
sensors (noisy) ──► ControllerInputs ──► Controller.step() ──► ControllerOutputs ──► vehicle
```

* `ControllerInputs` / `ControllerOutputs` are flat lists of numbers defined
  in one file. The same definition generates the C header for
  software-in-the-loop, so Python and C cannot drift apart.
* Controllers: `direct` (throttle straight to motors, for physics tests),
  `reference` (readable Python version of the STM32G4 logic: ride modes,
  blending, traction control, torque vectoring, regen, limits),
  `sil` (real C code compiled for the PC, loaded through `ctypes`).
* The rider's brake levers, steering and gear shifts act on the vehicle
  mechanically. Whether the petrol throttle is a cable or a servo is a
  parameter (`engine.throttle_by_wire`).

## 7. Scenarios, driver, batch

* A scenario is a YAML file: route segments (straight, arc, slalom, lane
  change, waypoints) with speed, surface (also left/right), gradient; wind;
  initial state; timed events (mode switches); end conditions; metrics.
* The driver model follows the route (pure-pursuit steering, speed planning
  with lateral/longitudinal acceleration limits, gear shifting).
* Batch: sweeps (1–2 parameters), Monte Carlo, optimiser (SciPy differential
  evolution) with hard safety constraints. Runs execute in parallel processes.
* Every run produces a safety report with time-stamped events.

## 8. Real data

* CSV logs, candump logs, SavvyCAN CSV. CAN decoding from an editable YAML
  message file (DBC-style); real `.dbc` files can be converted.
* Column-mapping wizard, saved mappings, resampling, alignment, filtering,
  gap handling.
* Replay drives the simulator with recorded throttle/brake/steering.
* Calibration fits chosen parameters with `scipy.optimize.least_squares`.
* All results carry a "not validated" label until the profile has been
  calibrated against real data.
* The example logs shipped in `data/example_logs/` are **generated by the
  simulator** (with hidden parameter changes and sensor noise) and are
  labelled as synthetic. No real measurements exist in this repository yet.

## 9. Phases

Exactly the seven phases in the project brief. `docs/PROGRESS.md` gets a
status note at the end of each phase.
