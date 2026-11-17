"""Speed of the simulator and things that would silently make it slow."""

import time

from helpers import scenario, straight

from bakbrommer_twin.params import ParamSet
from bakbrommer_twin.physics.inputs import RiderInputs
from bakbrommer_twin.sim.simulator import Simulation

# A 10-minute ride must simulate in well under a minute, i.e. faster than 10x real
# time. The limit here is deliberately loose (6x) so a busy test machine does not fail.
MIN_REAL_TIME_FACTOR = 6.0


def _simulation(params: ParamSet) -> Simulation:
    return Simulation(params, scenario(
        [straight(300, speed_kmh=35), {"type": "arc", "radius_m": 20, "angle_deg": 180,
                                       "speed_kmh": 30}, straight(600, speed_kmh=45)],
        end={"time_limit_s": 20.0}))


def test_simulation_is_much_faster_than_real_time(params: ParamSet) -> None:
    simulation = _simulation(params)
    start = time.perf_counter()
    result = simulation.run()
    wall = time.perf_counter() - start
    assert result.meta.duration == 20.0 and result.meta.time_step == 0.001
    assert result.meta.duration / wall > MIN_REAL_TIME_FACTOR, (
        f"only {result.meta.duration / wall:.1f}x real time")


def test_no_numpy_numbers_reach_the_step_loop(params: ParamSet) -> None:
    # NumPy scalars in the per-step maths make it several times slower (CLAUDE.md).
    simulation = _simulation(params)
    simulation.run()
    rider: RiderInputs = simulation.rider
    vehicle = simulation.vehicle
    values = {
        "rider.throttle": rider.throttle, "rider.brake_front": rider.brake_front,
        "rider.steer": rider.steer, "chassis.u": vehicle.chassis.u,
        "chassis.roll": vehicle.chassis.roll, "wheel.omega": vehicle.wheels[0].omega,
        "wheel.load": vehicle.wheels[0].load, "wheel.ground": vehicle.wheels[0].ground,
        "engine.speed": vehicle.engine.speed, "battery.voltage": vehicle.battery.voltage,
        "motor.torque": vehicle.drive_left.torque,
        "commands.torque_left": simulation.commands.torque_left,
        "inputs.wheel_speed_fl": simulation.inputs.wheel_speed_fl,
        "env.grade_sin": simulation.env.grade_sin,
    }
    wrong = {name: type(value).__name__ for name, value in values.items()
             if type(value) not in (float, int)}
    assert not wrong, f"these should be plain Python floats: {wrong}"
