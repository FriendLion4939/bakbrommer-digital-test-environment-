"""The parameter registry and every definition in it."""

import pytest

from bakbrommer_twin.params import REGISTRY, Kind, ParamError, Registry, Status


def test_registry_is_not_empty() -> None:
    assert len(REGISTRY) > 20


def test_every_definition_is_complete() -> None:
    for d in REGISTRY:
        assert d.label.strip(), d.name
        assert len(d.description.strip()) >= 10, f"{d.name} needs a real description"
        assert d.category in REGISTRY.categories(), d.name
        if d.kind in (Kind.NUMBER, Kind.CURVE, Kind.INTEGER):
            assert d.min is not None and d.max is not None, d.name
        # the default must pass its own validation
        assert REGISTRY.validate(d.name, d.default) is not None or d.kind is Kind.FLAG


def test_values_are_stored_in_si() -> None:
    d = REGISTRY.get("geometry.wheelbase")
    assert d.unit == "m" and d.si_unit == "m"
    assert d.default == pytest.approx(1.60)


def test_friendly_unit_is_converted_once() -> None:
    reg = Registry()
    reg.category("x", "X")
    reg.number("x.speed", 36.0, "km/h", 0.0, 72.0, "Speed", "A test speed value.")
    d = reg.get("x.speed")
    assert d.default == pytest.approx(10.0)
    assert d.max == pytest.approx(20.0)
    assert d.si_unit == "m/s"


def test_unknown_name_suggests_alternatives() -> None:
    with pytest.raises(ParamError, match=r"geometry\.wheelbase"):
        REGISTRY.get("geometry.wheelbas")


def test_duplicate_and_undeclared_category_rejected() -> None:
    reg = Registry()
    with pytest.raises(ParamError, match="category"):
        reg.flag("x.on", True, "On", "A test switch value.")
    reg.category("x", "X")
    reg.flag("x.on", True, "On", "A test switch value.")
    with pytest.raises(ParamError, match="twice"):
        reg.flag("x.on", True, "On", "A test switch value.")


def test_validation_of_each_kind() -> None:
    reg = Registry()
    reg.category("x", "X")
    reg.number("x.n", 1.0, "m", 0.0, 2.0, "N", "A test number value.")
    reg.integer("x.i", 3, 1, 5, "I", "A test integer value.")
    reg.flag("x.f", True, "F", "A test switch value.")
    reg.choice("x.c", "a", ["a", "b"], "C", "A test choice value.")
    reg.curve("x.k", [1.0, 2.0], "m", 0.0, 5.0, "K", "A test curve value.", Status.MEASURED)
    assert reg.validate("x.n", 2) == 2.0
    assert reg.validate("x.i", 4.0) == 4
    assert reg.validate("x.k", [1, 2, 3]) == [1.0, 2.0, 3.0]
    for name, bad in [("x.n", 3.0), ("x.n", "1"), ("x.n", True), ("x.i", 2.5), ("x.i", 9),
                      ("x.f", 1), ("x.c", "z"), ("x.k", [1.0]), ("x.k", [1.0, 9.0]),
                      ("x.n", float("nan"))]:
        with pytest.raises(ParamError):
            reg.validate(name, bad)  # type: ignore[arg-type]


def test_range_error_message_uses_friendly_unit() -> None:
    reg = Registry()
    reg.category("x", "X")
    reg.number("x.speed", 36.0, "km/h", 0.0, 72.0, "Speed", "A test speed value.")
    with pytest.raises(ParamError, match=r"100 km/h is outside the allowed range 0 … 72 km/h"):
        reg.validate("x.speed", 100 / 3.6)
