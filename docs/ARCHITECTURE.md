# Architecture

A map of the code for maintainers. Decisions and their reasons are in
`docs/PLAN.md`; equations are in `docs/PHYSICS.md`; step-by-step recipes are
in `docs/HOW_TO_CHANGE.md`.

## Layers (who may import whom)

```
ui ─► reports ─► batch / calibration / data_import ─► sim ─► scenarios ─► control, sensors ─► physics ─► params
```

A package may import packages to its right, never to its left. `physics`
knows nothing about scenarios, controllers or the UI.

## Module map

### `bakbrommer_twin/params/` — parameters
| File | What it does |
|---|---|
| `units.py` | The only unit conversion table (friendly unit ↔ SI). |
| `types.py` | `ParamDef`, `Status`, `Kind`. |
| `registry.py` | `Registry`: declares and validates parameters. |
| `definitions/*.py` | **Every parameter is declared here**, one file per category. Also the name lists (`SURFACE_NAMES`, `RIDE_MODES`, `SENSOR_SPECS`, …). |
| `paramset.py` | `ParamSet`: one complete set of values (SI) with typed accessors. |
| `profile.py` | Profiles as YAML: load/save, inheritance, history, compare. |
| `derived.py` | Calculated values shown in the UI. |

### `bakbrommer_twin/physics/` — the vehicle model (one file per subsystem)
| File | What it does |
|---|---|
| `mass.py` | Mass, CoG, inertia from components; static loads; rigid stability limits. |
| `lookup.py` | `Curve`: fast 1-D lookup table. |
| `surfaces.py` | Road surface properties prepared for the tyre model. |
| `tyres.py` | `Tyre`: magic formula, combined slip, relaxation. |
| `wheels.py` | `Wheel`: per-wheel state, spin dynamics, friction-as-constraint. |
| `steering.py` | `Steering`: centre-pivot and Ackermann geometry. |
| `chassis.py` | `Chassis`: 6-DOF rigid body, wheel contact, integration. |
| `motors.py` | `ElectricDrive`: hub motor + Fardriver, losses, thermal. |
| `battery.py` | `Battery`: Thevenin model, SoC, heat, BMS. |
| `engine.py` | `Engine`: torque, idle, rev limit, fuel. |
| `gearbox.py` | `Driveline`: gears/CVT, centrifugal clutch, engine–wheel solver. |
| `brakes.py` | `Brakes`: hydraulic pressure → torque. |
| `aero.py` | `Aero`: drag, side force, wind. |
| `energy.py` | `EnergyLedger`: energy bookkeeping. |
| `inputs.py` | `RiderInputs`, `DriveCommands`, `Environment` records. |
| `vehicle.py` | `Vehicle`: wires all subsystems; `step()` advances one time step. |
| `performance.py` | Steady-state estimates (top speed, gear speeds) for derived values. |

### `bakbrommer_twin/sensors/`
| File | What it does |
|---|---|
| `model.py` | `Sensor` (noise, bias, resolution, rate, delay), `NoiseSource`. |
| `suite.py` | `SensorSuite`: which true value each sensor measures; fills `ControllerInputs`. |

### `bakbrommer_twin/control/`
| File | What it does |
|---|---|
| `interface.py` | `ControllerInputs`, `ControllerOutputs`, `Controller` protocol — the brain's boundary. |
| `direct.py` | `DirectController`: throttle straight to the motors. |
| `factory.py` | `create_controller()`: picks the implementation from the parameters. |

### `bakbrommer_twin/scenarios/`
| File | What it does |
|---|---|
| `scenario.py` | Scenario file schema (`Scenario`, `Segment`, …) and `ScenarioStore`. |
| `route.py` | `Route`: segments → sampled path with attributes. |
| `driver.py` | `RouteDriver`: speed plan, pure-pursuit steering, pedals, gears. |
| `metrics.py` | Scenario-specific results (time to speed, braking distance, …). |

### `bakbrommer_twin/sim/`
| File | What it does |
|---|---|
| `simulator.py` | `Simulation`: the loop. `run_scenario()` convenience wrapper. |
| `road.py` | `Road`: surface per wheel, gradient, bumps, wind. |
| `channels.py` | Every recorded signal (`ChannelDef` + getter). |
| `safety.py` | `SafetyMonitor`: time-stamped safety events; `rollover_margin()`. |
| `summary.py` | Summary numbers for every run. |
| `result.py` | `RunResult`, `RunMeta`: results in memory and on disk. |

### Other
| Path | What it does |
|---|---|
| `bakbrommer_twin/ui/` | Streamlit web interface (`app.py`, `pages/`, `i18n.py`, `translations/`). |
| `bakbrommer_twin/paths.py` | Where data and results are stored. |
| `bakbrommer_twin/cli.py` | Command line (`ui`, `params`, `derived`, `scenarios`, `run`). |
| `data/profiles/`, `data/scenarios/` | Vehicle profiles and the scenario library (YAML). |
| `tests/` | pytest suite. `helpers.py` has the test rig; `reference/` holds regression numbers. |
| `scripts/check.sh`, `scripts/update_reference.py` | Quality gate; regenerate regression numbers. |

## One simulation step (`sim/simulator.py` → `physics/vehicle.py`)

```
Road.update            surface per wheel, bumps, gradient, wind   → Wheel.surface/ground, Environment
RouteDriver.update     (at driver.update_rate) position+speed     → RiderInputs
SensorSuite.sample     true states → noisy readings (own rates)
Controller.step        (at control.loop_rate) ControllerInputs    → ControllerOutputs → DriveCommands
Vehicle.step:
  Steering.apply       handlebar angle → wheel angles/positions
  Brakes.update        levers → pressures → brake torque capacity
  Chassis.contacts     body state → wheel loads, lift gaps, contact velocities
  Tyre.update ×3       slip states → tyre forces
  ElectricDrive.step×2 torque command → motor torque, bus current, heat
  Battery.step         total current → voltage, SoC, BMS
  Wheel.spin ×2        front wheel speeds (friction as constraint)
  Engine.update        throttle → crank torque, fuel
  Driveline.update/solve  gear/clutch → engine speed + rear wheel speed
  Aero.update          air forces
  Chassis.integrate    all forces → new body state
  Vehicle._account     energy ledger
(at sim.log_rate)      SafetyMonitor.update, record channels, end conditions
```

## How a parameter travels

```
params/definitions/*.py ──► REGISTRY ──► ParamSet (defaults)
                                           ▲
data/profiles/*.yaml ── ProfileStore.load ─┘ (base profile first, then overrides)
                                           │  + scenario param_overrides
              physics / control / sensors read values in their constructors
              UI builds its form from REGISTRY and edits the ParamSet
```

## Where does a change belong?

| I want to… | Go to |
|---|---|
| add or change a parameter | `params/definitions/<category>.py` |
| add a unit | `params/units.py` |
| change a physical model | the one file in `physics/` for that subsystem |
| change how subsystems interact | `physics/vehicle.py` |
| add a recorded signal | `sim/channels.py` |
| add a safety check | `sim/safety.py` |
| add a summary number | `sim/summary.py` |
| add a scenario | a YAML file in `data/scenarios/` |
| add a scenario metric type | `scenarios/metrics.py` |
| change the simulated rider | `scenarios/driver.py` |
| add a controller | `control/` + `control/factory.py` |
| add a calculated value to the UI | `params/derived.py` |
| change a UI text | `ui/translations/en.yaml` |
| add a UI page | `ui/pages/` + `PAGES` in `ui/app.py` |
