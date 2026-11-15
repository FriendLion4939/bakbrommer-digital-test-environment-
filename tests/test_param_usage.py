"""Every declared parameter must actually be read by the program.

The test builds everything that reads parameters and then asks the parameter
set which names were accessed. A parameter that nothing reads is dead weight
(or a sign that a model forgot to use it).
"""

from bakbrommer_twin.params import REGISTRY, ParamSet
from bakbrommer_twin.params.derived import compute_derived


def _exercise_everything(params: ParamSet) -> None:
    """Construct every consumer of parameters. Extend when adding a subsystem."""
    compute_derived(params)


def test_every_parameter_is_used(params: ParamSet) -> None:
    _exercise_everything(params)
    unused = sorted(set(REGISTRY.names()) - params.accessed_names())
    assert not unused, f"Declared but never read: {unused}"
