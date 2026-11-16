# Physics model

What the simulator calculates, with the equations and where they live in the
code. Everything is in SI units. Each source file repeats its equations in
comments; this document gives the overview and the reasoning.

**Honesty note.** All default values are estimates until measured (see the
status flag of each parameter). The model structure is standard vehicle
dynamics, but the numbers it produces are only as good as the parameters.
Results carry a "not validated" label until a profile has been calibrated
against real ride data.

## 1. Frames and sign conventions

| Frame | Definition |
|---|---|
| Design frame (parameters) | Origin on the ground under the middle of the front axle. `x` backwards, `y` left, `height` up. |
| Body frame (physics) | Origin at the centre of gravity (CoG). `x` forward, `y` left, `z` up. |
| World frame | `X`, `Y` in the road plane, `Z` along the road normal. |
| Level frame | World frame turned by the yaw angle. |

* Angles are right-handed: positive yaw/steer = left turn, positive pitch =
  nose down, positive roll = left side up (leaning to the right).
* Wheel order: 0 front-left, 1 front-right, 2 rear.
* A gradient does not tilt the road; it tilts gravity
  (`physics/vehicle.py`): the in-plane part `g·sin γ` points downhill along
  the route, the normal part is `g·cos γ`.

## 2. Mass properties — `physics/mass.py`

Five components (chassis, battery, rider, cargo, fuel) with mass and position.

* CoG: `r = Σ mᵢ·rᵢ / Σ mᵢ`.
* Inertia about the CoG (parallel-axis theorem): `I = Σ (Iᵢ,own + mᵢ·dᵢ²)`.
  Chassis: `m·k²` per axis (radius of gyration). Rider: one gyradius. Cargo:
  solid box `m/12·(a² + b²)`. Battery and fuel: point masses. Products of
  inertia are neglected.
* Static wheel loads (three wheels are statically determinate):
  `F_rear = m·g·x_cog/L`, `F_fl − F_fr = m·g·y_cog/(t/2)`.
* Rigid-vehicle wheel-lift limit (tipping about the line outer-front-tyre →
  rear tyre): `a_y = g·[(t/2)·(1 − x_cog/L) ± y_cog] / h_cog`.
* Tip-over angle: `atan(d/h_cog)`, `d` = distance from the CoG to that line.

## 3. Chassis — `physics/chassis.py`

One rigid body with six degrees of freedom. Newton–Euler equations in the
rotating body frame (principal axes):

```
m·(u̇ + q·w − r·v) = F_x      I_xx·ṗ + (I_zz − I_yy)·q·r = M_x
m·(v̇ + r·u − p·w) = F_y      I_yy·q̇ + (I_xx − I_zz)·r·p = M_y
m·(ẇ + p·v − q·u) = F_z      I_zz·ṙ + (I_yy − I_xx)·p·q = M_z
```

Orientation by Z-Y-X Euler angles (yaw ψ, pitch θ, roll φ).

**Wheel contact.** Each wheel is a vertical spring-damper along the road
normal that can only push:

```
δ  = road height − height of the unloaded tyre bottom      (compression)
F_z = max(0, k·δ + c·δ̇)   while δ > 0,   else 0
```

This one rule produces load transfer in pitch and roll, wheel lift (δ ≤ 0:
the wheel carries nothing and the gap −δ is its lift height) and rollover
(the roll angle simply keeps growing). No special formulas are needed.

Tyre forces act at the contact point on the road. Simplification: the
reaction of the drive/brake torque on the body is not applied separately,
which is exact whenever the wheel's spin speed is steady.

**Integration.** Semi-implicit Euler: forces → new velocities → new
positions. Stable for the vertical springs while `√(k/m)·dt < 2`
(default: about 0.05).

## 4. Tyres — `physics/tyres.py`, `physics/surfaces.py`

Simplified magic formula (Pacejka) with combined slip by normalised slips:

```
s_x = κ'/κ_peak,   s_y = tan α'/tan α_peak,   s = √(s_x² + s_y²)
F/(μ·F_z) = sin(C·atan(B·s))
F_x = μ·F_z·(F/…)·s_x/s        F_y = μ·r_lat·F_z·(F/…)·s_y/s
```

* The surface sets `μ` (peak friction), the sliding/peak ratio (→ shape
  `C = 2 − (2/π)·asin(ratio)`), and the peak position (`B = tan(π/(2C))`
  puts the peak at `s = 1`; the peak-slip scale stretches `κ_peak`, `α_peak`).
* Load sensitivity: `μ_eff = μ/(1 + k·(F_z/F_z,nom − 1))`.
* Relaxation (Pacejka 2nd ed., §7.2.3): the slips follow the kinematic slip
  with a first-order lag over the relaxation length σ:
  `σ·κ̇' + |V_x|·κ' = r·ω − V_x`, `σ·(tan α')̇ + |V_x|·tan α' = −V_y`.
  At standstill these are springs, which is what holds a parked vehicle.
* Low-speed damping (Pacejka §8.6): extra slip proportional to the sliding
  speed, fading out linearly up to the low-speed threshold.
* Rolling resistance moment: `c_rr·(1 + k_v·v²)·F_z·r` (part of the wheel
  friction, below).

Not modelled: camber thrust, aligning moment, tyre enveloping of short bumps.

## 5. Wheel spin and friction as a constraint — `physics/wheels.py`, `physics/gearbox.py`

`I·ω̇ = T_drive − r·F_x − T_friction`

Brake torque, rolling resistance and drag are *dry friction*: they oppose
motion with at most their capacity, and hold the wheel still if they can.
Each step the code computes the torque that would stop the wheel exactly
(`T_stop = I·ω_free/dt`) and applies it limited to ±capacity. This is
unconditionally stable and a held wheel stands exactly still.

The clutch is the same kind of constraint between engine and rear wheel
(`T_lock` brings the slip speed to zero, limited to the clutch capacity).
Clutch and rear-wheel friction are solved together by three Gauss–Seidel
passes.

The tyre's low-speed damping couples `F_x` to `ω` within a step; it is
treated implicitly by using `I + dt·r²·(F_x/κ)·d` as inertia.

## 6. Electric drive — `physics/motors.py`

Permanent-magnet motor under field-oriented control:

```
T = K_t·I_q                     back-EMF  E = K_e·ω,  K_e = K_t/1.5
phase current limit:  T ≤ K_t·I_peak·derate
voltage limit:        I_q ≤ (m·V_bus·f_w − K_e·|ω|)/R
line current limit:   (T·ω + 1.5·R·I_q²)/η_c + P_standby ≤ V_bus·I_line
```

Losses: copper `1.5·R(T)·I_q²`, drag torque `d0 + d1·|ω|`, controller
efficiency, standby power. The efficiency map is derived from these.
Regeneration uses the same equations with negative torque, a charge current
limit and a fade-out at low speed. Thermal: one node,
`C·Ṫ = P_cu + P_drag − G0·(1 + k·v)·(T − T_air)`, linear derating between the
derating start and the maximum temperature.

Simplifications: field weakening only stretches the speed range (its extra
current is not modelled); no reverse drive.

## 7. Battery — `physics/battery.py`

Thevenin circuit: `V = OCV(SoC) − I·R0 − V1`, `V̇1 = (I·R1 − V1)/τ`,
`SoĊ = −I/Q`. `R0` rises below 25 °C. Heat `I²·R0 + V1²/R1` into one thermal
node. The BMS disconnects the pack when the current stays beyond a limit for
longer than the trip delay, and reconnects after the reset time.

## 8. Petrol engine — `physics/engine.py`

Mean-value model: `T = load·(T_wot(ω) + T_f(ω)) − T_f(ω)` with
`T_f = f0 + f1·ω`. `load` follows the throttle with a lag; an idle system adds
load below idle speed; the rev limiter cuts it. Fuel (Willans line):
`fuel power = load·(T_wot + T_f)·ω / η_i`, never less than the idle flow.

## 9. Gearbox and clutch — `physics/gearbox.py`

Total ratio `R = primary × gear × final`. Manual: drive is interrupted for
the shift time. CVT: the belt ratio follows the ratio that would put the
engine at its target speed, with a lag. Centrifugal clutch capacity:
`T_max·clamp((ω² − ω_engage²)/(ω_lock² − ω_engage²), 0, 1)`. Driveline
efficiency η applies in both directions of power flow.

## 10. Brakes — `physics/brakes.py`

`T = 2·μ_pad·A_piston·p·r_eff` per wheel; pressure follows the lever with a
first-order lag; one front circuit (both front calipers) and one rear
circuit, optionally linked.

## 11. Aerodynamics — `physics/aero.py`

`F_x = −½ρ·Cd·A·|v_rel|·v_rel,x`, `F_y = −½ρ·Cs·A_side·|v_rel|·v_rel,y`, acting
at the centre of pressure (pitch, roll and yaw moments). `v_rel` includes the
wind. Cd is chosen by the cargo box shape.

## 12. Steering, road and rider

**Steering geometry — `physics/steering.py`.** `centre_pivot`: the whole
front axle turns about one pin; both wheels get the same angle and their
contact points move (`(d, y_w) → (d·cos δ − y_w·sin δ, d·sin δ + y_w·cos δ)`),
which shifts the tipping line. `ackermann`: positions fixed, inner wheel
steers more (`δ_in/out = atan(L·tan δ / (L ∓ (t/2)·tan δ))`), blended by the
Ackermann percentage. Tilting is an extension point described in the file.

**Road — `sim/road.py`.** Per wheel: surface (left / right / centre track of
the route) and road height. Roughness is a sum of four sine waves in the
distance the wheel has rolled, scaled so the RMS height equals the surface's
roughness height; every wheel has its own random phases (seeded). Gradient
tilts gravity; wind is a constant velocity vector.

**Wheel lift and rollover.** Nothing special is computed: when the inner
front wheel's spring is fully extended its load is zero and the gap is the
lift height. A rigid three-wheeler on two wheels is an inverted pendulum —
unless the rider reacts it rolls over in about a second. The simulator shows
exactly that when `driver.lift_reaction_gain` is 0.

**Rider — `scenarios/driver.py`.** Speed plan (segment speed, cornering limit
`√(a_lat/|κ|)`, backward braking pass), PI speed control, pure-pursuit
steering `δ = atan(L·2·y_l/L_d²)`. Wheel-lift reaction: beyond a roll angle
the rider steers out with a PD law on roll, closes the throttle, brakes
lightly, and keeps the cornering demand below the vehicle's rigid lift limit
until a recovery time after touchdown. This reproduces "one wheel in the air
and it keeps driving".

**Safety measures — `sim/safety.py`.** Rollover margin
`1 − |F_fl − F_fr|/(F_fl + F_fr)` (1 = even, 0 = one front wheel unloaded).
Events with start/end/peak: wheel lift, wheel spin, wheel lock, sideways
slide, battery over-current/over-charge/under-voltage, BMS trip, motor
derating/overheat, battery overheat, roll beyond the static tip-over angle,
rollover (run stops).

## 13. Sensors — `sensors/`

`reading = round((true + bias + noise)/resolution)·resolution`, refreshed at
the sensor's rate and delivered after its delay. The accelerometer reports
specific force (acceleration minus gravity) in body axes; the IMU is assumed
to sit at the CoG, aligned with the body.

## 14. Energy bookkeeping — `physics/energy.py`

Every step the vehicle adds each power flow to a ledger. Check used in the
tests and shown with every run:

```
Δ(kinetic + spring energy) = motor work + engine work + gravity work
                             − (brake + rolling + drag + clutch + gears
                                + air + tyre slip + dampers)
```

Typical error: below 0.1 % of the energy that flowed through the vehicle.

## 15. Numerical method

* Fixed step, default 1 ms. Tested from 0.5 ms to 2 ms.
* Stiff parts are handled implicitly: tyre relaxation decay, tyre low-speed
  damping, all dry friction (brakes, rolling resistance, clutch).
* The per-step code uses plain Python floats and attribute access only. No
  NumPy values may enter the loop (they make it several times slower); the
  route builder converts everything to plain floats for this reason.

## 16. Known simplifications

* No camber thrust and no wheel gyroscopic moments.
* No suspension kinematics: tyre and suspension are one vertical spring-damper
  per wheel, fixed to the body.
* Point contact with the road (no tyre enveloping).
* Drive/brake torque reaction on the body is neglected (exact at steady wheel
  speed).
* Centre-pivot steering moves the wheel contact points but not the cargo
  mass that sits on the turning axle (a few centimetres of CoG shift at
  large steering angles).
* The rider does not lean or shift weight.
* The fuel mass does not change during a run.
* IMU at the CoG.
