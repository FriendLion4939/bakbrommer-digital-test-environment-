"""Lookup curve."""

import pytest

from bakbrommer_twin.physics.lookup import Curve


def test_interpolates_and_clamps() -> None:
    curve = Curve([0.0, 1.0, 3.0], [0.0, 10.0, 30.0])
    assert curve(0.5) == pytest.approx(5.0)
    assert curve(2.0) == pytest.approx(20.0)
    assert curve(-5.0) == 0.0
    assert curve(99.0) == 30.0
    assert curve(1.0) == pytest.approx(10.0)
    assert (curve.x_min, curve.x_max, curve.y_max()) == (0.0, 3.0, 30.0)


@pytest.mark.parametrize(("xs", "ys"), [([0, 1], [1]), ([0], [1]), ([0, 0], [1, 2]),
                                        ([1, 0], [1, 2])])
def test_bad_points_are_rejected(xs: list[float], ys: list[float]) -> None:
    with pytest.raises(ValueError, match="my curve"):
        Curve(xs, ys, "my curve")
