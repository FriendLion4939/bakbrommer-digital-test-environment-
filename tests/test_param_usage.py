"""Every declared parameter must actually be read by the program.

The test builds everything that reads parameters and then asks the parameter
sets which names were accessed. A parameter that nothing reads is dead weight
(or a sign that a model forgot to use it).
"""

import pytest

from bakbrommer_twin.control.sil import build as sil_build
from bakbrommer_twin.params import REGISTRY, Kind, ParamSet
from bakbrommer_twin.params.derived import compute_derived
from bakbrommer_twin.scenarios.scenario import Scenario
from bakbrommer_twin.sim.simulator import Simulation

_SCENARIO = Scenario.model_validate(
    {"name": "usage", "route": [{"type": "straight", "length_m": 10.0}]})


def _exercise_everything(params: ParamSet, run: bool = False) -> set[str]:
    """Construct every consumer of parameters. Extend when adding a subsystem."""
    compute_derived(params)
    simulation = Simulation(params, _SCENARIO)
    if run:
        simulation.run()
    return params.accessed_names() | simulation.params.accessed_names()


def _needs_missing_compiler(name: str, option: str) -> bool:
    """The C (SIL) controller cannot be built without a C compiler, e.g. on a
    plain Windows PC. It reads no parameter of its own, so skipping it there
    loses nothing (``test_sil_controller_reads_no_parameter_of_its_own``)."""
    return (name, option) == ("control.controller_type", "sil") and (
        sil_build.find_compiler() is None)


def test_every_parameter_is_used(params: ParamSet) -> None:
    used = _exercise_everything(params, run=True)
    # Some parameters are only read for one option of a choice: try every option.
    for definition in REGISTRY:
        if definition.kind is Kind.CHOICE:
            for option in definition.choices:
                if _needs_missing_compiler(definition.name, option):
                    continue
                variant = params.copy()
                variant.set(definition.name, option)
                used |= _exercise_everything(variant)
    unused = sorted(set(REGISTRY.names()) - used)
    assert not unused, f"Declared but never read: {unused}"


def test_sil_controller_reads_no_parameter_of_its_own(params: ParamSet) -> None:
    if sil_build.find_compiler() is None:
        pytest.skip("no C compiler on this machine")
    sil = params.copy()
    sil.set("control.controller_type", "sil")
    reference = params.copy()
    assert _exercise_everything(sil) <= _exercise_everything(reference)
