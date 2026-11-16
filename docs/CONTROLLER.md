# The controller under test

The "brain" of the vehicle is the STM32G4. In the simulator it is a pluggable
module behind a fixed boundary, so the same vehicle model can be driven by
readable Python logic, by a trivial pass-through, or (Phase 6) by the real C
code compiled for the PC.

## The boundary — `control/interface.py`

```
sensors (noisy) ─► ControllerInputs ─► Controller.step(inputs, outputs) ─► ControllerOutputs ─► vehicle
```

* `ControllerInputs`: what the G4 can know — throttle, brake pressures,
  steering angle, engine speed, vehicle speed, three wheel speeds, IMU
  (accelerometer and gyro), battery voltage and current, motor temperatures,
  mode switch position, time step.
* `ControllerOutputs`: torque command per front motor, petrol throttle (used
  only with `engine.throttle_by_wire`), ignition enable, starter, the active
  mode, and diagnostic values for the charts.
* Both are flat lists of numbers in SI units — they map one-to-one onto two C
  structs of `double`.
* The rider's brake levers, steering, gear lever and (with a cable throttle)
  the petrol throttle act on the vehicle directly; the controller only sees
  their sensors.

Choose the implementation with the parameter `control.controller_type`:

| Value | What it is |
|---|---|
| `reference` | The hybrid logic described below (default). |
| `direct` | Throttle × `control.direct.max_torque` to both motors. For physics tests. |
| `sil` | C code compiled for the PC (`docs/SIL.md`). |

## The reference controller — `control/reference/`

One control period (`controller.py`), default 1000 times per second:

| Step | Block (file) | What it does |
|---|---|---|
| 1 | `estimator.py` | Speed estimate: slowest wheel while driving, fastest while braking, front wheels corrected for yaw rate, rate-limited by the accelerometer. |
| 2 | `modes.py` | Ride mode settings; a mode change glides over `control.mode_blend_time`. |
| 3 | `engine_manager.py` | Petrol engine OFF → CRANKING → RUNNING; start above the mode's start speed, stop after a delay when unwanted. |
| 4 | `controller.py`, `regen.py` | Torque request per motor = mode torque × throttle^exponent, faded out with speed while the engine runs; or regen (coast + brake pressure). |
| 5 | `limits.py` (`StabilityLimiter`) | Rollover protection: less drive torque as sideways acceleration approaches the limit, or on a roll-rate trigger. |
| 6 | `vectoring.py` | Left/right split: more torque to the outer wheel in proportion to sideways acceleration, plus a yaw-rate correction. |
| 7 | `slip.py` | Traction control (spin) and regen anti-lock (lock) per front wheel: PI limiter on wheel slip. |
| 8 | `limits.py` (`PowerLimiter`) | Battery current (prediction + feedback on measured current), low voltage, motor temperature. |
| 9 | `controller.py` | Torque rate limit. |

### Ride modes (defaults — all adjustable under "Controller")

| Setting | Normal | Eco | Sport | Standalone electric |
|---|---|---|---|---|
| Motor torque at full throttle | 45 Nm | 30 Nm | 80 Nm | 115 Nm |
| Throttle curve exponent | 1.0 | 1.5 | 0.8 | 1.0 |
| Electric assist fades (engine running) | 45→60 km/h | 25→40 km/h | never | never |
| Regen, closed throttle / full brake | 4 / 30 Nm | 8 / 30 Nm | 0 / 20 Nm | 6 / 40 Nm |
| Petrol engine | on | on above 15 km/h | on | off |
| Share of battery current limit | 90 % | 70 % | 100 % | 100 % |

"Standalone electric" keeps the petrol engine switched off and gives the
motors their full torque. Switching back to a hybrid mode cranks the engine
and the centrifugal clutch blends it in.

### Things the simulation showed while building this

* The brake pressure sensor is noisy; "braking" must be detected above a
  threshold (`control.regen.brake_threshold`), not at zero, or regen flickers
  on while accelerating.
* Near standstill, wheel speed noise can make "torque × speed" negative. The
  limiter must decide drive/regen from the torque sign, not from the power.
* When the rider closes the throttle to change gear, the controller sees a
  closed throttle and applies coast regen for a moment. With a cable throttle
  it cannot know better.
* With the 35 A BMS the electric drive is limited by the battery, not by the
  motors: Sport and Normal accelerate almost the same above 20 km/h. The
  profile "Future battery (150 A BMS)" shows what the upgrade brings.

## Real C code (software-in-the-loop)

`control.controller_type = sil` runs controller code written in C, compiled
for the PC, through the same boundary. See `docs/SIL.md`.
