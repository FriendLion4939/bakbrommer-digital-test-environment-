"""Parameter registry, parameter sets, profiles and derived values.

``REGISTRY`` is the one registry instance used by the whole program.
"""

from bakbrommer_twin.params.definitions import build_registry
from bakbrommer_twin.params.paramset import ParamSet
from bakbrommer_twin.params.registry import Registry
from bakbrommer_twin.params.types import Kind, ParamDef, ParamError, ParamValue, Status

REGISTRY: Registry = build_registry()


def default_params() -> ParamSet:
    """A parameter set holding the registry defaults."""
    return ParamSet(REGISTRY)


__all__ = [
    "REGISTRY",
    "Kind",
    "ParamDef",
    "ParamError",
    "ParamSet",
    "ParamValue",
    "Registry",
    "Status",
    "default_params",
]
