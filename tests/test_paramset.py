"""ParamSet: typed access, validation, copies and differences."""

import pytest

from bakbrommer_twin.params import ParamError, ParamSet, Status


def test_typed_access(params: ParamSet) -> None:
    assert params.num("geometry.wheelbase") == pytest.approx(1.6)
    with pytest.raises(ParamError, match="not a flag"):
        params.flag("geometry.wheelbase")
    with pytest.raises(ParamError, match="Unknown parameter"):
        params.num("geometry.nonsense")


def test_set_validates_and_tracks_status(params: ParamSet) -> None:
    params.set("mass.cargo.mass", 50.0, Status.MEASURED)
    assert params.num("mass.cargo.mass") == 50.0
    assert params.status("mass.cargo.mass") is Status.MEASURED
    with pytest.raises(ParamError, match="outside the allowed range"):
        params.set("mass.cargo.mass", -1.0)
    assert params.num("mass.cargo.mass") == 50.0


def test_copy_is_independent(params: ParamSet) -> None:
    other = params.copy()
    other.set("mass.rider.mass", 95.0)
    assert params.num("mass.rider.mass") == 80.0
    assert params.value_differences(other) == ["mass.rider.mass"]


def test_status_change_counts_as_difference(params: ParamSet) -> None:
    other = params.copy()
    other.set_status("geometry.wheelbase", Status.MEASURED)
    assert other.differences(params) == ["geometry.wheelbase"]
    assert other.value_differences(params) == []


def test_display_overrides(params: ParamSet) -> None:
    changed = params.with_display_overrides({"mass.cargo.mass": 40})
    assert changed.num("mass.cargo.mass") == 40.0
    assert params.num("mass.cargo.mass") == 0.0
    assert changed.as_display_dict()["mass.cargo.mass"] == 40.0


def test_accessed_names_are_recorded(params: ParamSet) -> None:
    params.num("geometry.wheelbase")
    assert params.accessed_names() == {"geometry.wheelbase"}
