"""Replay of a recorded ride, "what if" replays, and calibration against a log.

The recording used here is the shipped *synthetic* example (see
data/example_logs/README.md): a simulated ride of a vehicle whose chassis
mass, rolling resistance, frontal area and battery resistance differ from the
default profile.
"""

from functools import lru_cache

import numpy as np
import pytest
from helpers import SHIPPED_DATA

from bakbrommer_twin.calibration.fit import accept, calibrate
from bakbrommer_twin.data_import import clean, csv_log
from bakbrommer_twin.data_import.mapping import MappingStore
from bakbrommer_twin.data_import.recording import Recording
from bakbrommer_twin.data_import.replay import FitQuality, fit_quality, replay
from bakbrommer_twin.params import ParamSet, Status, default_params
from bakbrommer_twin.params.profile import Profile
from bakbrommer_twin.reports.chart_defs import charts_for_channels
from bakbrommer_twin.reports.figures import route_map, time_series

TRUTH = {"mass.chassis.mass": 150.0, "tyre.rolling_resistance_scale": 1.3,
         "aero.frontal_area": 1.15, "battery.internal_resistance": 85.0}


@lru_cache(maxsize=1)
def _recording() -> Recording:
    text = (SHIPPED_DATA / "example_logs" / "example_ride_sd.csv").read_text(encoding="utf-8")
    mapping = MappingStore(SHIPPED_DATA / "mappings").load("example_sd_card")
    recording, _ = clean.clean(csv_log.apply_mapping(csv_log.read_table(text), mapping, "sd"))
    return recording


def _short(seconds: float) -> Recording:
    full = _recording()
    count = round(seconds * full.rate)
    return Recording(full.source, full.rate, {k: v[:count] for k, v in full.data.items()})


def _quality(rows: list[FitQuality]) -> dict[str, FitQuality]:
    return {row.channel: row for row in rows}


def test_replay_follows_the_recorded_ride() -> None:
    result = replay(default_params(), _recording(), name="Example replay")
    assert result.meta.end_reason == "time_limit"
    assert result.meta.duration == pytest.approx(_recording().duration, abs=0.02)
    assert result.meta.scenario["category"] == "replay"
    # the rider inputs are reproduced exactly (apart from sensor noise in the log)
    assert np.nanmax(np.abs(result["throttle"] - result["meas_throttle"])) < 0.25
    quality = _quality(fit_quality(result))
    assert quality["steering_angle"].r_squared > 0.98
    assert quality["vehicle_speed"].r_squared > 0.9  # close, though the vehicle is "wrong"
    assert quality["gyro_z"].r_squared > 0.9
    labels = {c.name: c for c in result.meta.channels}
    assert labels["meas_vehicle_speed"].label.startswith("Measured")
    assert labels["meas_vehicle_speed"].unit == "km/h"


def test_replay_with_the_true_parameters_fits_better() -> None:
    recording = _short(45.0)
    wrong = _quality(fit_quality(replay(default_params(), recording, ideal_sensors=True)))
    right = _quality(fit_quality(replay(default_params(), recording, ideal_sensors=True,
                                        overrides=TRUTH)))
    for channel in ("vehicle_speed", "battery_voltage", "battery_current"):
        assert right[channel].rmse < wrong[channel].rmse, channel
    assert right["vehicle_speed"].r_squared > 0.995
    assert right["battery_voltage"].r_squared > 0.9


def test_what_if_replay_changes_the_outcome() -> None:
    recording = _short(25.0)
    baseline = replay(default_params(), recording)
    weaker = replay(default_params(), recording,
                    overrides={"control.mode_normal.electric_torque": 15.0})
    assert weaker["speed"].max() < baseline["speed"].max() - 0.3
    assert weaker.meta.params["control.mode_normal.electric_torque"] == 15.0
    assert np.array_equal(weaker["throttle"], baseline["throttle"])  # same rider inputs
    assert weaker.meta.energy["battery_chemical"] < baseline.meta.energy["battery_chemical"]


def test_replay_overlay_charts_and_route_map_work() -> None:
    result = replay(default_params(), _short(10.0))
    charts = charts_for_channels(result, ["sens_vehicle_speed", "meas_vehicle_speed",
                                          "sens_battery_current", "meas_battery_current"])
    assert [len(c.channels) for c in charts] == [2, 2]
    assert len(time_series([result], charts).data) == 4
    assert len(route_map([result]).data) == 1  # no planned route for a replay


def test_replay_needs_a_throttle_channel_and_tolerates_missing_others() -> None:
    full = _short(8.0)
    with pytest.raises(ValueError, match="throttle"):
        replay(default_params(), Recording("x", full.rate, {"vehicle_speed":
                                                            full.data["vehicle_speed"]}))
    minimal = Recording("x", full.rate, {"throttle": full.data["throttle"]})
    result = replay(default_params(), minimal)
    assert result["speed"].max() > 3.0 and result["steer"].max() == 0.0


def test_calibration_recovers_hidden_values(params: ParamSet) -> None:
    # Two of the four hidden values are given; the fit must find the other two.
    params.set_display("tyre.rolling_resistance_scale", TRUTH["tyre.rolling_resistance_scale"])
    params.set_display("aero.frontal_area", TRUTH["aero.frontal_area"])
    calls: list[int] = []
    result = calibrate(params, _short(40.0),
                       ["mass.chassis.mass", "battery.internal_resistance"],
                       ["vehicle_speed", "battery_voltage"], max_evaluations=18,
                       progress=lambda count, cost: calls.append(count))
    assert result.fitted["battery.internal_resistance"] == pytest.approx(85.0, rel=0.10)
    assert result.fitted["mass.chassis.mass"] == pytest.approx(150.0, rel=0.10)
    assert result.start == {"mass.chassis.mass": 130.0, "battery.internal_resistance": 60.0}
    before, after = _quality(result.before), _quality(result.after)
    assert after["battery_voltage"].rmse < 0.6 * before["battery_voltage"].rmse
    assert after["vehicle_speed"].rmse < before["vehicle_speed"].rmse
    assert calls and calls[-1] == result.evaluations <= 18 + 3
    assert not result.at_limit

    profile = Profile("test", "Test", params)
    accept(profile, result, synthetic=True)
    assert not profile.validated  # a fit to synthetic data validates nothing
    accept(profile, result, synthetic=False)
    assert profile.validated
    assert profile.params.status("mass.chassis.mass") is Status.CALIBRATED
    assert profile.params.display("battery.internal_resistance") == result.fitted[
        "battery.internal_resistance"]


def test_calibration_checks_its_inputs(params: ParamSet) -> None:
    recording = _short(5.0)
    with pytest.raises(ValueError, match="at least one"):
        calibrate(params, recording, [], ["vehicle_speed"])
    with pytest.raises(ValueError, match="cannot be calibrated"):
        calibrate(params, recording, ["steering.type"], ["vehicle_speed"])
    with pytest.raises(ValueError, match="no usable"):
        calibrate(params, Recording("x", 100.0, {"throttle": recording.data["throttle"]}),
                  ["mass.chassis.mass"], ["vehicle_speed"])
