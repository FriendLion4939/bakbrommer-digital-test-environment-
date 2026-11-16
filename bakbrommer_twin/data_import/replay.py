"""Replay: drive the simulated vehicle with the rider inputs of a real ride.

The recorded throttle, brake pressure, steering angle and ride mode are fed
into the simulator; everything else (speed, wheel speeds, yaw rate, battery
current …) is simulated and can be laid over the measurement.

The gear is usually not logged. It is worked out from the measured engine
speed and rear wheel speed (their ratio is the gear ratio while the clutch
grips); without those channels the simulated rider shifts by engine speed.

What a replay cannot know: the road. It assumes level ground and the profile's
default surface. Steering is replayed open-loop, so the simulated path slowly
drifts away from the real one — compare speeds, rates and currents, not
positions. For the same reason nobody "catches" the simulated vehicle: if its
parameters make it clearly faster than the real one in a corner ridden near
the wheel-lift limit, it can lift a wheel or roll over where the real vehicle
did not. That is a sign the parameters are off, not a fault of the ride.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from bakbrommer_twin.data_import.channels import LOG_CHANNELS, MODE_CHANNEL
from bakbrommer_twin.data_import.recording import Recording
from bakbrommer_twin.params import units
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.types import ParamValue
from bakbrommer_twin.physics.gearbox import Driveline
from bakbrommer_twin.physics.inputs import RiderInputs
from bakbrommer_twin.physics.vehicle import Vehicle
from bakbrommer_twin.scenarios.driver import shift_gears
from bakbrommer_twin.scenarios.route import Route
from bakbrommer_twin.scenarios.scenario import REPLAY_CATEGORY, Scenario
from bakbrommer_twin.sim.result import ChannelInfo, RunResult
from bakbrommer_twin.sim.simulator import ProgressCallback, Simulation

MEASURED_PREFIX = "meas_"
Array = NDArray[np.float64]


def infer_gears(params: ParamSet, recording: Recording) -> list[int] | None:
    """Gear at every sample, from measured engine speed / rear wheel speed.

    While the clutch is fully engaged, engine speed = total ratio × wheel
    speed, so the gear is the one whose ratio is nearest to the measured
    ratio. Below the clutch's full-grip speed the last known gear is kept. A
    change is accepted only after it has persisted for the shift time (sensor
    noise must not cause phantom shifts). Returns None when the channels are
    missing or the gearbox is a CVT.
    """
    if not {"engine_speed", "wheel_speed_r"} <= set(recording.data):
        return None
    driveline = Driveline(params)
    if driveline.is_cvt:
        return None
    ratios = np.array([driveline.total_ratio(g) for g in range(1, driveline.gear_count + 1)])
    engine = recording.filled("engine_speed")
    wheel = recording.filled("wheel_speed_r")
    locked = (engine > params.num("clutch.lockup_speed")) & (wheel > 0.0)
    measured = np.divide(engine, wheel, out=np.zeros_like(engine), where=wheel > 0.0)
    nearest = np.argmin(np.abs(np.log(np.maximum(measured[:, None], 1e-9) / ratios[None, :])),
                        axis=1) + 1
    hold = max(1, round(driveline.shift_time * recording.rate))
    gears, current, candidate, streak = [], 1, 1, 0
    for is_locked, gear in zip(locked.tolist(), nearest.tolist(), strict=True):
        if is_locked and gear != current:
            streak = streak + 1 if gear == candidate else 1
            candidate = gear
            if streak >= hold:
                current, streak = gear, 0
        else:
            streak = 0
        gears.append(current)
    # The new ratio is noticed one hold time after the gear went in, and the rider moved
    # the lever one shift time before that: move every change two hold times earlier.
    lead = 2 * hold
    return gears[lead:] + [gears[-1]] * lead if len(gears) > lead else gears


class ReplayDriver:
    """Plays recorded rider inputs back into the vehicle."""

    def __init__(self, params: ParamSet, recording: Recording) -> None:
        self.route_index = 0
        self.target_speed = 0.0
        self.rate = recording.rate
        self.upshift = params.num("driver.upshift_speed")
        self.downshift = params.num("driver.downshift_speed")
        count = recording.samples

        def channel(name: str) -> Array:
            return recording.filled(name) if name in recording.data else np.zeros(count)

        # Lever position = measured pressure / pressure at full lever. Readings below the
        # brake detection threshold are sensor noise, not braking (otherwise the noise
        # would act as a small permanent brake).
        threshold = params.num("control.regen.brake_threshold")

        def lever(name: str, full_pressure: float) -> Array:
            pressure = channel(name)
            return np.where(pressure > threshold, pressure, 0.0) / full_pressure

        front = lever("brake_front_pressure", params.num("brakes.front_max_pressure"))
        if "brake_rear_pressure" in recording.data:
            rear = lever("brake_rear_pressure", params.num("brakes.rear_max_pressure"))
        else:  # not logged: assume the rider's usual front/rear habit
            rear = front * params.num("driver.rear_brake_ratio")
        self._throttle: list[float] = np.clip(channel("throttle"), 0.0, 1.0).tolist()
        self._front: list[float] = np.clip(front, 0.0, 1.0).tolist()
        self._rear: list[float] = np.clip(rear, 0.0, 1.0).tolist()
        self._steer: list[float] = channel("steering_angle").tolist()
        self._mode: list[int] = np.rint(channel(MODE_CHANNEL)).astype(int).tolist()
        self._speed: list[float] = channel("vehicle_speed").tolist()
        self._gears = infer_gears(params, recording)
        self._last = count - 1
        self._time = 0.0

    def update(self, dt: float, vehicle: Vehicle, rider: RiderInputs) -> None:
        """Copy the recorded inputs of the present time into the rider inputs."""
        index = min(self._last, round(self._time * self.rate))
        rider.throttle = self._throttle[index]
        rider.brake_front = self._front[index]
        rider.brake_rear = self._rear[index]
        rider.steer = self._steer[index]
        rider.mode_request = self._mode[index]
        self.target_speed = self._speed[index]
        if self._gears is None:
            shift_gears(vehicle, rider, self.upshift, self.downshift)
        else:  # the recorded throttle already contains the rider lifting off to shift
            rider.gear = self._gears[index]
        self._time += dt


def replay(params: ParamSet, recording: Recording, *, name: str = "Replay",
           profile_name: str = "", validated: bool = False,
           overrides: Mapping[str, ParamValue] | None = None, ideal_sensors: bool = False,
           progress: ProgressCallback | None = None) -> RunResult:
    """Simulate the recorded ride and attach the measurement to the result.

    ``overrides`` (friendly units) change parameters for this replay only —
    this is the "what if" tool. Measured channels appear in the result as
    ``meas_<channel>`` next to the simulated ``sens_<channel>``.
    """
    if "throttle" not in recording.data:
        raise ValueError("a replay needs at least the throttle channel")
    changed = dict(overrides or {})
    if ideal_sensors:
        changed["sensors.ideal"] = True
    start_speed = 0.0
    if "vehicle_speed" in recording.data:
        start_speed = max(0.0, float(recording.filled("vehicle_speed")[0]))
    scenario = Scenario.model_validate({
        "name": name, "category": REPLAY_CATEGORY,
        "description": f"Replay of {recording.source}", "param_overrides": changed,
        "route": [{"type": "straight", "length_m": 1.0}],
        "initial": {"speed_kmh": start_speed * 3.6},
        "end": {"time_limit_s": max(recording.duration, 1.0 / recording.rate)}})
    used = params.with_display_overrides(changed)
    route = Route.open_area(used.choice("environment.default_surface"),
                            used.num("sim.route_sample_spacing"))
    simulation = Simulation(params, scenario, profile_name=profile_name, validated=validated,
                            name=name, route=route, driver=ReplayDriver(used, recording))
    result = simulation.run(progress)
    attach_measurement(result, recording)
    return result


def attach_measurement(result: RunResult, recording: Recording) -> None:
    """Add the recording's channels to a result as ``meas_<channel>`` (NaN where missing)."""
    index = np.rint(result["time"] * recording.rate).astype(int)
    inside = index < recording.samples
    for name, values in recording.data.items():
        channel = LOG_CHANNELS[name]
        sampled = np.full(len(index), np.nan)
        sampled[inside] = values[index[inside]]
        key = f"{MEASURED_PREFIX}{name}"
        result.data[key] = sampled
        result.meta.channels.append(ChannelInfo(
            name=key, unit=channel.unit, label=f"Measured: {channel.title}", group="Measured"))


@dataclass(frozen=True)
class FitQuality:
    """How well the simulation matches one measured channel."""

    channel: str
    title: str
    unit: str
    samples: int
    rmse: float  # root-mean-square error, SI
    bias: float  # mean(simulated − measured), SI
    r_squared: float  # 1 = perfect, 0 = no better than the mean, < 0 = worse


def fit_quality(result: RunResult) -> list[FitQuality]:
    """Compare every measured channel of a replay result with its simulated twin."""
    rows = []
    for item in result.meta.channels:
        if not item.name.startswith(MEASURED_PREFIX):
            continue
        name = item.name[len(MEASURED_PREFIX):]
        simulated = result.data.get(LOG_CHANNELS[name].sim_channel)
        measured = result.data[item.name]
        valid = np.isfinite(measured)
        if simulated is None or valid.sum() < 2:
            continue
        error = simulated[valid] - measured[valid]
        spread = float(np.sum((measured[valid] - measured[valid].mean()) ** 2))
        r_squared = 1.0 - float(np.sum(error**2)) / spread if spread > 0.0 else 0.0
        rows.append(FitQuality(name, LOG_CHANNELS[name].title, item.unit, int(valid.sum()),
                               float(np.sqrt(np.mean(error**2))), float(error.mean()),
                               r_squared))
    return rows


def quality_table_rows(rows: list[FitQuality]) -> list[dict[str, object]]:
    """Fit quality as table rows with errors converted to each channel's friendly unit."""
    table = []
    for row in rows:
        factor = units.UNITS[row.unit][1]  # errors are differences: scale only, no offset
        table.append({"channel": row.title, "unit": row.unit, "samples": row.samples,
                      "rmse": float(f"{row.rmse / factor:.4g}"),
                      "bias": float(f"{row.bias / factor:.4g}"),
                      "r_squared": round(row.r_squared, 4)})
    return table
