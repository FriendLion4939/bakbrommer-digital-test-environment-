"""Software-in-the-loop: generated header, compiling, and the C example in the loop."""

from pathlib import Path

import pytest
from helpers import scenario, straight

from bakbrommer_twin.control.interface import ControllerInputs, ControllerOutputs
from bakbrommer_twin.control.sil import build as sil_build
from bakbrommer_twin.control.sil.bridge import SilController
from bakbrommer_twin.control.sil.header import HEADER_PATH, header_text
from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.sim.simulator import run_scenario

needs_compiler = pytest.mark.skipif(sil_build.find_compiler() is None,
                                    reason="no C compiler on this machine")


def test_committed_header_matches_the_python_interface() -> None:
    assert HEADER_PATH.read_text(encoding="utf-8") == header_text(), (
        "run: python -m bakbrommer_twin.control.sil.header")
    text = header_text()
    assert "double wheel_speed_fl;  /* rad/s */" in text
    assert "double torque_left;" in text and "bb_step(const bb_inputs_t *in" in text


@needs_compiler
def test_build_is_cached_and_reports_compile_errors(tmp_path: Path) -> None:
    first = sil_build.build(output_dir=tmp_path)
    assert first.exists() and sil_build.build(output_dir=tmp_path) == first
    broken = tmp_path / "broken.c"
    broken.write_text('#include "bb_controller.h"\nint oops( {', encoding="utf-8")
    with pytest.raises(sil_build.SilBuildError, match=r"broken\.c failed"):
        sil_build.build(broken, tmp_path)
    with pytest.raises(sil_build.SilBuildError, match="not found"):
        sil_build.build(tmp_path / "missing.c", tmp_path)


@needs_compiler
def test_c_controller_gets_parameters_by_name_and_computes_torque(params: ParamSet) -> None:
    params.set_display("control.mode_normal.electric_torque", 50.0)
    controller = SilController(params)
    assert "control.limits.battery_current" in controller.param_names
    inputs = ControllerInputs(dt=0.001, throttle=0.5, battery_voltage=66.0)
    outputs = ControllerOutputs()
    for _ in range(1000):  # long enough to pass the rate limit
        controller.step(inputs, outputs)
    assert outputs.torque_left == outputs.torque_right == pytest.approx(25.0)
    assert outputs.engine_ignition == 1.0 and outputs.engine_throttle == 0.5
    # fast wheels: the predicted current exceeds the limit and torque is scaled down
    inputs.wheel_speed_fl = inputs.wheel_speed_fr = 60.0
    for _ in range(1000):
        controller.step(inputs, outputs)
    limit = params.num("control.limits.battery_current")
    efficiency = params.num("control.limits.assumed_efficiency")
    expected = limit * efficiency * 66.0 / (2 * 60.0)
    assert outputs.torque_left == pytest.approx(expected, rel=1e-6)
    assert outputs.diag_power_limit < 1.0
    # braking gives regen; reset clears the state
    inputs.throttle, inputs.brake_front_pressure = 0.0, params.num("control.regen.full_pressure")
    for _ in range(1000):
        controller.step(inputs, outputs)
    assert outputs.torque_left == pytest.approx(
        -params.num("control.mode_normal.brake_regen_torque"))
    controller.reset()
    inputs.brake_front_pressure = 0.0
    controller.step(inputs, outputs)
    assert abs(outputs.torque_left) < 1.0


@needs_compiler
def test_c_controller_drives_the_simulated_vehicle(params: ParamSet) -> None:
    params.set("control.controller_type", "sil")
    result = run_scenario(params, scenario(
        [straight(400, throttle=1.0)], end={"time_limit_s": 20, "at_speed_kmh": 40},
        metrics=[{"type": "time_to_speed", "speed_kmh": 40}]))
    assert result.meta.controller == "sil"
    assert result.meta.end_reason == "speed_reached"
    assert 3.0 < (result.metric("time_0_40") or 0.0) < 10.0
    assert result.metric("bms_trips") == 0.0
    assert result["ctl_torque_left"].max() == pytest.approx(
        params.num("control.mode_normal.electric_torque"), rel=0.01)
