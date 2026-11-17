# Bakbrommer Twin

A driving simulator and "digital twin" for a hybrid three-wheeled cargo moped:
two electric hub motors at the front, a petrol engine at the rear. You
describe the vehicle with numbers, pick a ride, and see what would happen —
speed, wheel loads, a front wheel lifting in a corner, battery current,
consumption — before trying it on the road.

Everything is operated in a web browser. No programming is needed.

> **Read this first.** The numbers the simulator ships with are estimates.
> Every result is labelled **NOT VALIDATED** until you have measured your
> vehicle and calibrated the profile against a real ride log. The example
> logs that come with the program are **synthetic** (made by the simulator
> itself) — they are for trying the tools, not for conclusions.

---

## 1. Install and start

Pick the way that fits you. You only need one.

### A. Windows PC

1. Install Python 3.12 or newer from <https://www.python.org/downloads/>.
   During installation tick **"Add python.exe to PATH"**.
2. Download this project (green "Code" button → "Download ZIP") and unpack it.
3. Double-click **`start.bat`**. The first start downloads what is needed and
   takes a few minutes; later starts take seconds.
4. Open <http://localhost:8501> in your browser.

To stop: close the black window.

### B. Linux or macOS

```bash
./start.sh
```

Then open <http://localhost:8501>. Stop with Ctrl+C. (Needs Python 3.12 or
newer.)

### C. Home server with Docker (Proxmox)

In a container or VM that has Docker, inside the project folder:

```bash
docker compose up -d --build
```

Then open `http://<address-of-the-server>:8501` from any PC or phone in your
network. Stop with:

```bash
docker compose down
```

Your own files (profiles, scenarios, imported logs, results) are kept in the
folder `userdata/` next to `docker-compose.yml`. Back up that folder.

---

## 2. First simulation (five minutes)

1. Open the page **Run a simulation** (menu on the left).
2. Choose the scenario **"Acceleration 0-50 km/h"** and press **Run**.
3. You get:
   * the headline numbers (time 0–50 km/h and so on),
   * the **safety report** (wheel lift, wheel spin, locked wheels, battery
     over-current … each with the time it happened),
   * **charts** — zoom into one and the others follow; add any signal with
     "Add any recorded signal",
   * the **Animation** tab — a top view of the vehicle. Dark wheels carry a lot
     of load, a red hollow wheel is in the air, arrows show the tyre forces,
   * the **Export** tab — CSV, a printable HTML report, a PDF report.
4. Now try **"Steady-state circle (find wheel-lift speed)"**. It tells you at
   which speed the inner front wheel lifts on a 12 m circle.

Every run is saved automatically. On **Results and comparison** tick one run
to open it again, or two or more to compare them side by side.

---

## 3. Make it your vehicle

Page **Parameters**. Every number the simulator uses is here, grouped in
categories, with a unit, an allowed range and a short explanation (the "?"
next to each field).

* Each value has a status: *measured*, *estimated*, *default (needs
  measuring)* or *calibrated*. Change it when you have measured something.
* **Calculated values** shows what follows from your numbers: total mass,
  centre of gravity, the cornering force at which a wheel lifts, gear speeds,
  top speed estimate.
* **Curves** shows the tyre, motor, engine and battery curves your numbers
  produce.
* A **profile** is a saved set of values. "Save as new profile" makes a copy,
  e.g. one for an empty box and one for a full one. **Compare profiles** shows
  the differences; **History** lets you go back to an earlier save.

What to measure first (it decides wheel lift): the weight on each wheel (three
bathroom scales), the height of the centre of gravity, track width and
wheelbase. Then the BMS and motor controller current limits as actually set.

Shipped profiles: *Default bakbrommer*, *Full cargo*, *Wet weather*, *Future
battery (150 A BMS)*.

---

## 4. Your own rides

Page **Scenarios**. A scenario is a route made of pieces (straight, bend,
slalom, lane change, free-drawn curve) with a speed, a road surface and a
gradient for each piece, plus what should be measured.

* Pick a built-in scenario to see how it is made, change it, and save it under
  a new file name.
* **Draw a route by clicking**: click points on the grid, then "Use this
  drawing as the route".
* The preview shows the route from above and the speed the simulated rider
  plans to ride.

---

## 5. Try many things at once

Page **Sweeps and optimiser**:

* **Parameter sweep** — e.g. cargo mass from 0 to 100 kg in 5 steps: how does
  the 0–50 time change?
* **Monte Carlo** — vary load, grip and so on at random: how much do results
  scatter, how often is a safety limit broken?
* **Optimiser** — let the program search controller settings for a goal
  (fastest, least energy …) while no safety limit is broken (no rollover,
  wheel lift limited, battery current below the BMS limit, motor temperature
  within limits).

---

## 6. Import a real ride log

Page **Import and replay a ride**.

1. **Choose a log file** — a CSV from the SD card, or a CAN log from the
   CANable adapter (candump `.log` or SavvyCAN `.csv`). To try it first, pick
   the shipped example `example_ride_sd.csv` (synthetic!).
2. **Tell the program what is in it.**
   * CSV: for each column choose the sensor and the unit. The program guesses
     from the column names; correct it and press **Save mapping** — next time
     you just pick the mapping from the list.
   * CAN: choose the definition file that describes your messages. The shipped
     one is only an example layout: open "View or edit this definition file"
     and make it match your firmware, or convert a `.dbc` file.
3. **Clean and check** — the table shows per channel how many values were
   impossible, where the log has gaps, and how much is usable.
4. **Replay this ride** — the simulator is given your throttle, brake and
   steering and you see simulated and measured speed, current, yaw rate …
   on top of each other, with numbers for how well they match.
5. **What if …?** — replay the same ride with a changed setting (for example a
   different motor torque) and see what would have been different.

Then page **Calibration**: choose a few uncertain values (mass, rolling
resistance, frontal area, battery resistance …) and the program adjusts them
until the replay matches the measurement. Check the before/after table, then
**Accept** and save the profile on the Parameters page. Only a calibration
against a *real* log removes the "NOT VALIDATED" label.

More detail: `docs/DATA_IMPORT.md`.

---

## 7. Good to know

* **Where are my files?** In the folder `data/` (profiles, scenarios, CAN
  definitions, mappings, recordings) and `runs/` (results). With Docker both
  are under `userdata/`. They are plain text files (YAML) you can copy and
  back up.
* **How fast is it?** A 10-minute ride simulates in about half a minute.
* **A run ends with "rolled over".** Then the simulated vehicle fell over. Look
  at the animation and the roll angle chart just before the end.
* **The petrol engine does not start / the electric motors do nothing.** Check
  the safety report: a tripped BMS or an empty battery switches the motors off.
* **Another language.** All texts are in
  `bakbrommer_twin/translations/en.yaml`. Copy it to `nl.yaml`, translate the
  right-hand sides, restart — "nl" appears in the language picker.
* **Testing your own controller code in C** (software-in-the-loop):
  `docs/SIL.md`.
* **Is everything still working?** Run the automatic tests:
  `./run_tests.sh` (Linux/macOS), `run_tests.bat` (Windows) or
  `docker compose run --rm bakbrommer-twin test`. It takes a few minutes and
  should end with "… passed". A few "skipped" tests are normal on a PC
  without a C compiler (they test the software-in-the-loop option).

## 8. For whoever maintains the code

| Read | For |
|---|---|
| `CLAUDE.md` | Rules and commands for maintainers (human or AI). |
| `docs/ARCHITECTURE.md` | Map of the code and of one simulation step. |
| `docs/HOW_TO_CHANGE.md` | Step-by-step recipes for the usual changes. |
| `docs/PHYSICS.md` | The equations and simplifications. |
| `docs/CONTROLLER.md`, `docs/SIL.md` | The controller under test and how to plug in C code. |
| `docs/DATA_IMPORT.md` | Import, replay and calibration. |
| `docs/PROGRESS.md` | What was built and checked in each phase, and known limits. |
