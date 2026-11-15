"""Profiles: YAML load/save, inheritance, history, copy, delete, compare."""

from pathlib import Path

import pytest
import yaml

from bakbrommer_twin.params import ParamError, Status
from bakbrommer_twin.params.profile import Profile, ProfileStore, compare


def test_shipped_profiles_load(store: ProfileStore) -> None:
    assert {"default", "full_cargo"} <= set(store.list_keys())
    for key in store.list_keys():
        assert store.load(key).name


def test_inheritance(store: ProfileStore) -> None:
    full = store.load("full_cargo")
    assert full.base == "default"
    assert full.params.num("mass.cargo.mass") == 80.0
    assert full.params.num("mass.rider.mass") == store.load("default").params.num(
        "mass.rider.mass")


def test_save_round_trip_stores_only_differences(store: ProfileStore) -> None:
    profile = store.load("full_cargo")
    profile.params.set("mass.rider.mass", 92.5, Status.MEASURED)
    profile.notes["mass.rider.mass"] = "weighed with gear"
    path = store.save(profile)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["values"]["mass.rider.mass"] == {
        "value": 92.5, "unit": "kg", "status": "measured", "note": "weighed with gear"}
    assert "geometry.wheelbase" not in raw["values"]
    again = store.load("full_cargo")
    assert again.params.differences(profile.params) == []
    assert again.notes == {"mass.rider.mass": "weighed with gear"}


def test_base_changes_flow_through(store: ProfileStore) -> None:
    base = store.load("default")
    base.params.set("geometry.wheelbase", 1.75)
    store.save(base)
    assert store.load("full_cargo").params.num("geometry.wheelbase") == 1.75


def test_entry_with_other_unit_and_short_form(store: ProfileStore) -> None:
    (store.directory / "odd.yaml").write_text(
        "name: Odd\nbase: default\nvalues:\n"
        "  geometry.wheelbase: {value: 1700, unit: mm}\n"
        "  mass.cargo.mass: 25\n", encoding="utf-8")
    odd = store.load("odd")
    assert odd.params.num("geometry.wheelbase") == pytest.approx(1.7)
    assert odd.params.num("mass.cargo.mass") == 25.0


@pytest.mark.parametrize("body", [
    "name: Bad\nvalues:\n  geometry.wheelbase: {value: 3, unit: kg}\n",
    "name: Bad\nvalues:\n  geometry.wheelbase: 99\n",
    "name: Bad\nvalues:\n  geometry.nope: 1\n",
    "name: Bad\nsurprise: 1\n",
])
def test_bad_files_are_rejected(store: ProfileStore, body: str) -> None:
    (store.directory / "bad.yaml").write_text(body, encoding="utf-8")
    with pytest.raises((ParamError, ValueError)):
        store.load("bad")


def test_circular_base_is_detected(store: ProfileStore) -> None:
    (store.directory / "a.yaml").write_text("name: A\nbase: b\n", encoding="utf-8")
    (store.directory / "b.yaml").write_text("name: B\nbase: a\n", encoding="utf-8")
    with pytest.raises(ParamError, match="circle"):
        store.load("a")


def test_history_and_restore(store: ProfileStore) -> None:
    profile = store.load("default")
    profile.params.set("mass.rider.mass", 70.0)
    store.save(profile)
    profile.params.set("mass.rider.mass", 75.0)
    store.save(profile)
    stamps = store.history("default")
    assert len(stamps) == 2 and stamps[0] > stamps[1]
    assert store.load_version("default", stamps[1]).params.num("mass.rider.mass") == 70.0


def test_copy_and_delete(store: ProfileStore) -> None:
    duplicate = store.copy("full_cargo", "full_cargo_2", "Copy")
    assert duplicate.params.num("mass.cargo.mass") == 80.0
    with pytest.raises(ParamError, match="already exists"):
        store.copy("full_cargo", "full_cargo_2", "Copy")
    with pytest.raises(ParamError, match="base of"):
        store.delete("default")
    store.delete("full_cargo_2")
    assert "full_cargo_2" not in store.list_keys()


def test_invalid_key(store: ProfileStore, tmp_path: Path) -> None:
    with pytest.raises(ParamError, match="lower-case"):
        store.save(Profile("Bad Name", "x", store.load("default").params))


def test_compare(store: ProfileStore) -> None:
    rows = compare(store.load("default").params, store.load("full_cargo").params)
    by_name = {r.name: r for r in rows}
    assert set(by_name) == {"mass.cargo.mass", "mass.cargo.height", "mass.cargo.stack_height"}
    assert by_name["mass.cargo.mass"].value_a == 0.0
    assert by_name["mass.cargo.mass"].value_b == 80.0
