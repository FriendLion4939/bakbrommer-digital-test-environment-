"""Fast one-dimensional lookup curve (piecewise linear, clamped at the ends)."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from itertools import pairwise


class Curve:
    """``y = f(x)`` by linear interpolation between points; flat outside the range."""

    __slots__ = ("_slopes", "_xs", "_ys")

    def __init__(self, xs: Sequence[float], ys: Sequence[float], name: str = "curve") -> None:
        if len(xs) != len(ys) or len(xs) < 2:
            raise ValueError(f"{name}: need the same number (at least 2) of x and y points, "
                             f"got {len(xs)} and {len(ys)}")
        if any(b <= a for a, b in pairwise(xs)):
            raise ValueError(f"{name}: x points must be strictly rising")
        self._xs = [float(x) for x in xs]
        self._ys = [float(y) for y in ys]
        self._slopes = [
            (self._ys[i + 1] - self._ys[i]) / (self._xs[i + 1] - self._xs[i])
            for i in range(len(xs) - 1)
        ]

    def __call__(self, x: float) -> float:
        xs = self._xs
        if x <= xs[0]:
            return self._ys[0]
        if x >= xs[-1]:
            return self._ys[-1]
        i = bisect_right(xs, x) - 1
        return self._ys[i] + self._slopes[i] * (x - xs[i])

    @property
    def x_min(self) -> float:
        """Smallest x point."""
        return self._xs[0]

    @property
    def x_max(self) -> float:
        """Largest x point."""
        return self._xs[-1]

    def y_max(self) -> float:
        """Largest y value of the curve."""
        return max(self._ys)
